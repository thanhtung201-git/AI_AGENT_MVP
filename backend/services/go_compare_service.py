"""
go_compare_service.py — So sánh GO (Garment Order) với PO (Purchase Order).

Logic:
  1. Lấy GO data (từ HZSH + GO Information)
  2. Lấy PO data (từ FormatUnderstander)
  3. So sánh: total_qty, colors, sizes, delivery date
  4. Trả về report với danh sách match/mismatch/missing

Output format:
  {
    "summary": {
      "status":          "OK" | "MISMATCH" | "PARTIAL",
      "go_total_qty":    1274,
      "po_total_qty":    1274,
      "qty_diff":        0,
      "matched_colors":  2,
      "mismatched_colors": 0,
      "missing_in_go":   [],
      "missing_in_po":   [],
    },
    "color_details": [
      {
        "color_code":    "N2",
        "color_name":    "NORMAL NAVY",
        "go_qty":        774,
        "po_qty":        774,
        "qty_diff":      0,
        "status":        "OK",
        "size_details":  [{"size": "00S", "go_qty": 191, "po_qty": 191, "diff": 0, "status": "OK"}],
      }
    ],
    "date_check": {
      "go_ship_date":  "2026-07-15",
      "po_delivery":   "2026-07-15",
      "date_match":    True,
    }
  }
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GOCompareService:
    """So sánh GO data với PO data, trả về report chi tiết."""

    def compare(
        self,
        go_data: Dict[str, Any],
        po_data: Dict[str, Any],
        hzsh_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        So sánh GO vs PO.

        Args:
            go_data:   output của GOExtractor.extract()["data"]
                       (có thể thiếu nếu không có file GO Information)
            po_data:   output của FormatUnderstander.extract()["data"]
            hzsh_data: output của HZSHExtractor.extract()["data"]
                       (dùng để bổ sung size/lot detail nếu go_data thiếu)

        Returns:
            dict với summary + color_details + date_check
        """
        # Merge GO + HZSH: HZSH thường chính xác hơn về size breakdown
        effective_go = self._merge_go_hzsh(go_data, hzsh_data)

        go_colors = self._index_colors(effective_go.get("colors", []))
        po_colors = self._index_po_colors(po_data)

        all_codes = sorted(set(list(go_colors.keys()) + list(po_colors.keys())))

        color_details = []
        total_go_qty  = 0
        total_po_qty  = 0
        n_ok = n_mismatch = 0

        for code in all_codes:
            go_c = go_colors.get(code)
            po_c = po_colors.get(code)

            go_qty = go_c["total_qty"] if go_c else 0
            po_qty = po_c["total_qty"] if po_c else 0
            diff   = go_qty - po_qty

            if not go_c:
                status = "MISSING_IN_GO"
                n_mismatch += 1
            elif not po_c:
                status = "MISSING_IN_PO"
                n_mismatch += 1
            elif diff == 0:
                status = "OK"
                n_ok += 1
            else:
                status = "MISMATCH"
                n_mismatch += 1

            size_details = self._compare_sizes(
                go_c.get("sizes", {}) if go_c else {},
                po_c.get("sizes", {}) if po_c else {},
            )

            color_details.append({
                "color_code":   code,
                "color_name":   (go_c or po_c or {}).get("color_name", ""),
                "go_qty":       go_qty,
                "po_qty":       po_qty,
                "qty_diff":     diff,
                "status":       status,
                "size_details": size_details,
            })

            total_go_qty += go_qty
            total_po_qty += po_qty

        qty_diff = total_go_qty - total_po_qty
        if qty_diff == 0 and n_mismatch == 0:
            overall_status = "OK"
        elif n_ok == 0:
            overall_status = "MISMATCH"
        else:
            overall_status = "PARTIAL"

        missing_in_go = [d["color_code"] for d in color_details if d["status"] == "MISSING_IN_GO"]
        missing_in_po = [d["color_code"] for d in color_details if d["status"] == "MISSING_IN_PO"]

        date_check = self._compare_dates(effective_go, po_data)

        logger.info(
            f"GOCompare: status={overall_status}, "
            f"go_qty={total_go_qty}, po_qty={total_po_qty}, diff={qty_diff}"
        )

        return {
            "summary": {
                "status":             overall_status,
                "go_number":          effective_go.get("go_number", ""),
                "po_number":          po_data.get("po_number", ""),
                "style_no":           effective_go.get("style_no", po_data.get("style_code", "")),
                "go_total_qty":       total_go_qty,
                "po_total_qty":       total_po_qty,
                "qty_diff":           qty_diff,
                "matched_colors":     n_ok,
                "mismatched_colors":  n_mismatch,
                "missing_in_go":      missing_in_go,
                "missing_in_po":      missing_in_po,
            },
            "color_details": color_details,
            "date_check":    date_check,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _merge_go_hzsh(
        self,
        go_data: Dict[str, Any],
        hzsh_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Merge HZSH vào GO: ưu tiên HZSH cho size breakdown."""
        if not hzsh_data:
            return go_data or {}

        merged = dict(go_data or {})

        # Dùng colors từ HZSH nếu có (size breakdown chính xác hơn)
        hzsh_colors = hzsh_data.get("colors", [])
        if hzsh_colors:
            merged["colors"] = hzsh_colors
            merged["total_qty"] = sum(c.get("total_qty", 0) for c in hzsh_colors)

        # Bổ sung style/season từ HZSH nếu GO thiếu
        for field in ("style_no", "season", "brand"):
            if not merged.get(field) and hzsh_data.get(field):
                merged[field] = hzsh_data[field]

        return merged

    def _index_colors(self, colors: List[Dict]) -> Dict[str, Dict]:
        """Index colors list theo color_code."""
        idx = {}
        for c in colors:
            code = c.get("color_code", "").strip().upper()
            if code:
                idx[code] = c
        return idx

    def _index_po_colors(self, po_data: Dict[str, Any]) -> Dict[str, Dict]:
        """
        Extract color+qty từ PO data.

        FormatUnderstander trả về:
          po_data["colors"] = [{"color_code", "color_name", "total_qty", "sizes"}]
        hoặc
          po_data["lots"]   = [{"color_code", "total_qty", "sizes"}]
        """
        colors = po_data.get("colors", [])
        if colors:
            return self._index_colors(colors)

        # Fallback: gộp lots theo color_code
        lots = po_data.get("lots", [])
        merged: Dict[str, Dict] = {}
        for lot in lots:
            code = (lot.get("color_code") or "").strip().upper()
            if not code:
                continue
            if code not in merged:
                merged[code] = {
                    "color_code": code,
                    "color_name": lot.get("color_name", ""),
                    "total_qty":  0,
                    "sizes":      {},
                }
            merged[code]["total_qty"] += lot.get("total_qty", 0)
            # Merge sizes
            for size, qty in (lot.get("sizes") or {}).items():
                merged[code]["sizes"][size] = merged[code]["sizes"].get(size, 0) + qty

        return merged

    def _compare_sizes(
        self, go_sizes: Dict[str, int], po_sizes: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """So sánh size breakdown."""
        if not go_sizes and not po_sizes:
            return []

        all_sizes = sorted(set(list(go_sizes.keys()) + list(po_sizes.keys())))
        details = []
        for size in all_sizes:
            go_q = go_sizes.get(size, 0) or 0
            po_q = po_sizes.get(size, 0) or 0
            diff = go_q - po_q
            details.append({
                "size":   size,
                "go_qty": go_q,
                "po_qty": po_q,
                "diff":   diff,
                "status": "OK" if diff == 0 else "MISMATCH",
            })
        return details

    def _compare_dates(
        self, go_data: Dict[str, Any], po_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """So sánh ngày giao hàng."""
        go_ship = go_data.get("ship_date") or go_data.get("cancel_date") or ""
        po_del  = po_data.get("delivery_date") or po_data.get("ship_date") or ""

        # So sánh đơn giản: nếu cả 2 có giá trị, so sánh chuỗi
        date_match: Optional[bool] = None
        if go_ship and po_del:
            date_match = (go_ship.strip() == po_del.strip())

        return {
            "go_ship_date": go_ship,
            "po_delivery":  po_del,
            "date_match":   date_match,
        }
