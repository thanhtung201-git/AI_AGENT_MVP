import logging
from typing import List, Dict, Any
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)


class TrimlistExporter:
    """Export Trimlist ra file Excel theo định dạng chuẩn ngành may."""

    # Màu header
    _HEADER_FILL  = PatternFill("solid", fgColor="1F3864")   # xanh đậm
    _SUBHDR_FILL  = PatternFill("solid", fgColor="2E75B6")   # xanh nhạt
    _ALT_FILL     = PatternFill("solid", fgColor="EBF3FB")   # xanh rất nhạt (xen kẽ)
    _TOTAL_FILL   = PatternFill("solid", fgColor="FFF2CC")   # vàng nhạt (total row)

    _THIN = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"),  bottom=Side(style="thin"),
    )

    @classmethod
    def export(
        cls,
        trim_items: List[Dict[str, Any]],
        output_path: str,
        meta: Dict[str, Any] = None,
    ) -> str:
        """
        Export danh sách trim ra Excel.

        Args:
            trim_items:  List dict từ TrimlistExtractor
            output_path: Đường dẫn file .xlsx
            meta:        Thông tin header (po_number, style_code, order_qty, ...)
        Returns:
            output_path
        """
        meta = meta or {}
        wb = Workbook()
        ws = wb.active
        ws.title = "Trimlist"

        row = 1

        # ── Tiêu đề file ─────────────────────────────────────────────────────
        ws.merge_cells(f"A{row}:I{row}")
        ws[f"A{row}"] = "TRIM LIST / DANH SÁCH PHỤ LIỆU"
        ws[f"A{row}"].font      = Font(bold=True, size=14, color="FFFFFF")
        ws[f"A{row}"].fill      = cls._HEADER_FILL
        ws[f"A{row}"].alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row].height = 28
        row += 1

        # ── Thông tin PO / Style ─────────────────────────────────────────────
        info_pairs = [
            ("PO Number",   meta.get("po_number", "")),
            ("Style Code",  meta.get("style_code", "")),
            ("Style Name",  meta.get("style_name", "")),
            ("Buyer",       meta.get("buyer", "")),
            ("Season",      meta.get("season", "")),
            ("Order Qty",   meta.get("order_qty", "")),
            ("Factory",     meta.get("factory", "")),
            ("Prepared by", meta.get("prepared_by", "AI Agent")),
            ("Date",        meta.get("date", "")),
        ]
        for i in range(0, len(info_pairs), 3):
            chunk = info_pairs[i:i+3]
            col = 1
            for label, value in chunk:
                ws.cell(row, col,   label).font = Font(bold=True, size=10)
                ws.cell(row, col,   label).fill = PatternFill("solid", fgColor="D6E4F0")
                ws.cell(row, col+1, str(value)).font = Font(size=10)
                col += 3
            row += 1

        row += 1  # khoảng trống

        # ── Header bảng trim ─────────────────────────────────────────────────
        columns = [
            ("No.",            5),
            ("Trim Item",      22),
            ("Spec / Material",30),
            ("Supplier",       20),
            ("Supplier Code",  18),
            ("Placement",      18),
            ("Qty/Garment",    13),
            ("Unit",            8),
            ("Total Qty",      13),
        ]
        for col_idx, (col_name, col_width) in enumerate(columns, 1):
            cell = ws.cell(row, col_idx, col_name)
            cell.font      = Font(bold=True, size=10, color="FFFFFF")
            cell.fill      = cls._SUBHDR_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border    = cls._THIN
            ws.column_dimensions[get_column_letter(col_idx)].width = col_width
        ws.row_dimensions[row].height = 22
        header_row = row
        row += 1

        # ── Dữ liệu trim ─────────────────────────────────────────────────────
        for idx, item in enumerate(trim_items, 1):
            fill = cls._ALT_FILL if idx % 2 == 0 else PatternFill()
            values = [
                idx,
                item.get("trim_item", ""),
                item.get("spec", ""),
                item.get("supplier", ""),
                item.get("supplier_code", ""),
                item.get("placement", ""),
                item.get("qty_per_garment", ""),
                item.get("unit", "pc"),
                item.get("total_qty", ""),
            ]
            for col_idx, val in enumerate(values, 1):
                cell = ws.cell(row, col_idx, val)
                cell.fill   = fill
                cell.border = cls._THIN
                cell.font   = Font(size=10)
                if col_idx in (1, 7, 8, 9):
                    cell.alignment = Alignment(horizontal="center")
            row += 1

        # ── Total row ────────────────────────────────────────────────────────
        ws.merge_cells(f"A{row}:F{row}")
        ws.cell(row, 1, "TOTAL").font      = Font(bold=True, size=10)
        ws.cell(row, 1, "TOTAL").fill      = cls._TOTAL_FILL
        ws.cell(row, 1, "TOTAL").alignment = Alignment(horizontal="right")

        total_qty_sum = sum(
            (it.get("total_qty") or 0) for it in trim_items
            if isinstance(it.get("total_qty"), (int, float))
        )
        ws.cell(row, 9, total_qty_sum).font      = Font(bold=True, size=10)
        ws.cell(row, 9, total_qty_sum).fill      = cls._TOTAL_FILL
        ws.cell(row, 9, total_qty_sum).alignment = Alignment(horizontal="center")
        for c in range(1, 10):
            ws.cell(row, c).border = cls._THIN

        # ── Freeze header ────────────────────────────────────────────────────
        ws.freeze_panes = ws.cell(header_row + 1, 1)

        wb.save(output_path)
        logger.info(f"Trimlist exported: {output_path} ({len(trim_items)} items)")
        return output_path
