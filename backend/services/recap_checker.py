"""
So sánh Đơn Đặt Hàng (PIC nhập) với Trimlist gốc.
Gắn cờ sai lệch theo các quy tắc nghiệp vụ.
"""
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Trạng thái
OK       = "OK"
ERROR    = "ERROR"
WARNING  = "WARNING"


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _supplier_root(s: str) -> str:
    return _normalize(s).split()[0] if _normalize(s) else ""


def _extract_measurements(spec: str) -> List[str]:
    """Lấy các số kèm đơn vị từ spec: '72cm', '5mm', '25mm'..."""
    return re.findall(r"\d+(?:\.\d+)?\s*(?:cm|mm|m\b|l\b|pcs?|sets?)", spec, re.IGNORECASE)


def check_order(
    order_items: List[Dict],
    trimlist_items: List[Dict],
    order_qty_total: int = 0,
) -> List[Dict]:
    """
    So sánh từng item trong đơn đặt hàng với trimlist gốc.

    Trả về list các item với thêm fields:
        status:   OK | WARNING | ERROR
        issues:   list string mô tả lỗi
        qty_required: số lượng cần theo trimlist
    """
    # Build lookup trimlist theo supplier_code
    trim_by_code = {}
    for t in trimlist_items:
        code = _normalize(t.get("supplier_code") or t.get("trim_code") or "")
        if code:
            trim_by_code[code] = t

    # Build lookup theo tên (fallback)
    trim_by_name = {}
    for t in trimlist_items:
        name = _normalize(t.get("trim_item") or "")
        if name:
            trim_by_name[name] = t

    results = []
    for item in order_items:
        issues  = []
        status  = OK

        code    = _normalize(item.get("supplier_code") or "")
        name    = _normalize(item.get("trim_item") or "")
        ref     = trim_by_code.get(code) or trim_by_name.get(name)

        qty_ordered  = float(item.get("qty_ordered") or 0)
        qty_required = 0

        if ref:
            # Tính qty_required từ trimlist
            qty_pg = float(ref.get("qty_per_garment") or 0)
            if order_qty_total and qty_pg:
                qty_required = round(qty_pg * order_qty_total, 2)
            elif ref.get("total_qty"):
                qty_required = float(ref.get("total_qty") or 0)

        # ── Kiểm tra 1: Qty = 0 ─────────────────────────────────────────
        if qty_ordered == 0:
            issues.append("❌ CHƯA ĐẶT — Số lượng = 0")
            status = ERROR

        # ── Kiểm tra 2: Qty lệch so với trimlist ────────────────────────
        elif qty_required > 0 and qty_ordered != qty_required:
            diff_pct = abs(qty_ordered - qty_required) / qty_required * 100
            if diff_pct > 5:
                issues.append(
                    f"❌ SAI SỐ LƯỢNG — Đặt {qty_ordered:g}, cần {qty_required:g} "
                    f"(lệch {diff_pct:.0f}%)"
                )
                status = ERROR
            else:
                issues.append(
                    f"⚠️ LỆCH NHỎ — Đặt {qty_ordered:g}, cần {qty_required:g}"
                )
                if status == OK:
                    status = WARNING

        # ── Kiểm tra 3: Supplier sai ────────────────────────────────────
        if ref:
            ref_supplier = _supplier_root(ref.get("supplier") or "")
            ord_supplier = _supplier_root(item.get("supplier") or "")
            if ref_supplier and ord_supplier and ref_supplier != ord_supplier:
                issues.append(
                    f"❌ SAI SUPPLIER — Đặt từ '{item.get('supplier')}', "
                    f"phải là '{ref.get('supplier')}'"
                )
                status = ERROR

        # ── Kiểm tra 4: Unit sai ────────────────────────────────────────
        if ref:
            ref_unit = _normalize(ref.get("unit") or "")
            ord_unit = _normalize(item.get("unit") or "")
            # Chuẩn hóa aliases
            alias = {"meters": "m", "meter": "m", "pcs": "pc", "pieces": "pc"}
            ref_unit = alias.get(ref_unit, ref_unit)
            ord_unit = alias.get(ord_unit, ord_unit)
            if ref_unit and ord_unit and ref_unit != ord_unit:
                issues.append(
                    f"❌ SAI ĐƠN VỊ — Đặt '{item.get('unit')}', phải là '{ref.get('unit')}'"
                )
                status = ERROR

        # ── Kiểm tra 5: Spec — số đo không khớp ────────────────────────
        if ref:
            ref_spec = ref.get("spec") or ""
            ord_spec = item.get("spec") or ""
            ref_measures = _extract_measurements(ref_spec)
            ord_measures = _extract_measurements(ord_spec)
            # So sánh từng số đo trong ref có xuất hiện trong ord không
            missing_measures = [
                m for m in ref_measures
                if m.replace(" ", "").lower() not in ord_spec.replace(" ", "").lower()
            ]
            if missing_measures and ord_spec:
                issues.append(
                    f"⚠️ NGHI NGỜ SPEC — Ref có '{', '.join(ref_measures)}' "
                    f"nhưng đơn ghi '{', '.join(ord_measures) or 'không rõ'}'"
                )
                if status == OK:
                    status = WARNING

        # ── Không tìm thấy trong trimlist ──────────────────────────────
        if not ref:
            issues.append("⚠️ KHÔNG CÓ TRONG TRIMLIST — Item thêm ngoài Trimlist gốc")
            if status == OK:
                status = WARNING

        results.append({
            **item,
            "qty_required": qty_required,
            "status":       status,
            "issues":       issues,
            "ref_supplier": ref.get("supplier") if ref else "",
            "ref_spec":     ref.get("spec") if ref else "",
        })

    return results


def summary_stats(checked_items: List[Dict]) -> Dict[str, Any]:
    total   = len(checked_items)
    ok      = sum(1 for i in checked_items if i["status"] == OK)
    errors  = sum(1 for i in checked_items if i["status"] == ERROR)
    warns   = sum(1 for i in checked_items if i["status"] == WARNING)
    return {
        "total":    total,
        "ok":       ok,
        "errors":   errors,
        "warnings": warns,
        "passed":   errors == 0,
    }
