"""
Đọc file Đơn Đặt Hàng Phụ Liệu (Excel do PIC nhập tay).
Trả về header info + danh sách items đã đặt.
"""
import pandas as pd
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class RecapExtractor:

    def extract(self, file_path: str) -> Dict[str, Any]:
        xl = pd.read_excel(file_path, sheet_name=0, header=None)
        rows = xl.values.tolist()

        # Đọc header (rows 2-5, col 0 = label, col 1 = value, col 2 = label, col 3 = value)
        def _val(r, c):
            try:
                v = rows[r][c]
                return str(v).strip() if pd.notna(v) else ""
            except Exception:
                return ""

        header = {
            "po_number":    _val(2, 1),
            "style_code":   _val(2, 3),
            "buyer":        _val(3, 1),
            "style_name":   _val(3, 3),
            "season":       _val(4, 1),
            "order_qty":    _val(4, 3),
            "factory":      _val(5, 1),
            "date_ordered": _val(5, 3),
        }

        # Tìm hàng header bảng (row chứa "No." hoặc "Supplier Code")
        data_start = None
        for i, row in enumerate(rows):
            vals = [str(v).strip().lower() for v in row if pd.notna(v)]
            if any("supplier code" in v or "trim item" in v for v in vals):
                data_start = i + 1
                break

        if data_start is None:
            logger.warning("Không tìm thấy header bảng trong file")
            return {"header": header, "items": []}

        items = []
        for row in rows[data_start:]:
            # Bỏ hàng trống
            vals = [v for v in row if pd.notna(v) and str(v).strip()]
            if len(vals) < 3:
                continue
            try:
                no            = str(row[0]).strip() if pd.notna(row[0]) else ""
                supplier_code = str(row[1]).strip() if pd.notna(row[1]) else ""
                trim_item     = str(row[2]).strip() if pd.notna(row[2]) else ""
                spec          = str(row[3]).strip() if pd.notna(row[3]) else ""
                supplier      = str(row[4]).strip() if pd.notna(row[4]) else ""
                qty_str       = str(row[5]).strip() if pd.notna(row[5]) else "0"
                unit          = str(row[6]).strip() if pd.notna(row[6]) else ""
                note          = str(row[7]).strip() if len(row) > 7 and pd.notna(row[7]) else ""

                try:
                    qty = float(qty_str)
                except (ValueError, TypeError):
                    qty = 0

                if not trim_item or trim_item.lower() in ("nan", "none", "trim item"):
                    continue

                items.append({
                    "no":             no,
                    "supplier_code":  supplier_code,
                    "trim_item":      trim_item,
                    "spec":           spec,
                    "supplier":       supplier,
                    "qty_ordered":    qty,
                    "unit":           unit,
                    "note":           note,
                })
            except Exception as e:
                logger.debug(f"Bỏ qua hàng lỗi: {e}")
                continue

        logger.info(f"RecapExtractor: đọc {len(items)} items từ {file_path}")
        return {"header": header, "items": items}
