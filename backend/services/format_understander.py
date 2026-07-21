"""
format_understander.py — 2-phase LLM để đọc bất kỳ Excel PO format nào.

Phase 1: Gửi sample tọa độ row/col → LLM trả về layout metadata
         (header ở row nào, field nào ở cột nào, data bắt đầu từ đâu...)
Phase 2: Dùng layout metadata để extract dữ liệu chính xác

Không hardcode vị trí → hoạt động với mọi format PO.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

_PHASE1_SYSTEM = """Bạn là chuyên gia phân tích cấu trúc bảng tính Excel trong ngành may mặc.

Nhiệm vụ: Đọc nội dung Excel được biểu diễn theo tọa độ row/col và xác định cấu trúc layout.

Trả về JSON với format:
{
  "sheet_name": "tên sheet chứa dữ liệu chính",
  "header_row": <số row chứa tên cột>,
  "data_start_row": <số row bắt đầu dữ liệu>,
  "field_map": {
    "po_number":    "<col_letter hoặc null>",
    "style_code":   "<col_letter hoặc null>",
    "style_name":   "<col_letter hoặc null>",
    "buyer":        "<col_letter hoặc null>",
    "season":       "<col_letter hoặc null>",
    "color_code":   "<col_letter hoặc null>",
    "color_name":   "<col_letter hoặc null>",
    "total_qty":    "<col_letter hoặc null>",
    "unit_price":   "<col_letter hoặc null>",
    "delivery_date":"<col_letter hoặc null>",
    "destination":  "<col_letter hoặc null>",
    "factory":      "<col_letter hoặc null>"
  },
  "size_columns": ["<col_letter>", ...],
  "layout_type": "vertical|horizontal|matrix",
  "notes": "ghi chú đặc biệt về layout nếu có"
}

Nếu dữ liệu nằm ở header file (không phải dạng bảng), hãy ghi rõ trong notes."""

_PHASE2_SYSTEM = """Bạn là chuyên gia đọc Purchase Order (PO) ngành may mặc.

Dựa vào layout metadata đã được phân tích, hãy extract dữ liệu từ Excel và trả về JSON:
{
  "po_number":     "...",
  "style_code":    "...",
  "style_name":    "...",
  "buyer":         "...",
  "season":        "...",
  "factory":       "...",
  "delivery_date": "...",
  "total_qty":     <số>,
  "colors": [
    {
      "color_code": "...",
      "color_name": "...",
      "sizes": {"00S": <qty>, "00M": <qty>, ...},
      "total_qty": <số>,
      "destination": "..."
    }
  ],
  "lots": [
    {
      "destination": "...",
      "customer":    "...",
      "color_code":  "...",
      "sizes": {"00S": <qty>, ...},
      "total_qty":   <số>
    }
  ]
}

Chỉ điền những field có dữ liệu thực. Bỏ qua field không tìm thấy (để null).
Trả về JSON thuần, không markdown."""


class FormatUnderstander:
    """
    2-phase LLM extraction — đọc bất kỳ Excel PO format nào.

    Usage:
        fu = FormatUnderstander()
        result = fu.extract(structured_data)
        # result: {"layout": {...}, "data": {...}}
    """

    def __init__(self):
        self.groq = GroqClient()

    def extract(self, structured: Dict[str, Any], sample_rows: int = 40) -> Dict[str, Any]:
        """
        Chạy 2-phase extraction trên structured Excel data.

        Args:
            structured: output của read_excel_structured() — dict với key "structured" và "text_repr"
            sample_rows: số row gửi LLM ở Phase 1 (giới hạn token)

        Returns:
            {
                "success": bool,
                "layout":  dict  — Phase 1 output,
                "data":    dict  — Phase 2 output (PO data),
                "error":   str | None
            }
        """
        text_repr = structured.get("text_repr", "")
        if not text_repr:
            return {"success": False, "layout": {}, "data": {}, "error": "Không có dữ liệu structured"}

        # Giới hạn sample để tránh tràn token Phase 1
        lines = text_repr.splitlines()
        sample = "\n".join(lines[:sample_rows * 3])  # ~3 dòng/row

        try:
            # ── Phase 1: hiểu layout ──────────────────────────────────────
            logger.info("FormatUnderstander Phase 1: phân tích layout...")
            layout = self.groq.extract_json(
                system_prompt=_PHASE1_SYSTEM,
                user_content=f"Phân tích cấu trúc layout của Excel PO sau:\n\n{sample}",
            )
            logger.info(f"Phase 1 layout: sheet={layout.get('sheet_name')}, "
                        f"header_row={layout.get('header_row')}, "
                        f"layout_type={layout.get('layout_type')}")

            # ── Phase 2: extract data với context từ Phase 1 ─────────────
            logger.info("FormatUnderstander Phase 2: extract dữ liệu...")

            # Lấy toàn bộ text của sheet được chỉ định
            target_sheet = layout.get("sheet_name", "")
            sheet_text = self._get_sheet_text(structured, target_sheet) or text_repr

            phase2_input = (
                f"Layout metadata:\n{json.dumps(layout, ensure_ascii=False, indent=2)}\n\n"
                f"Nội dung Excel:\n{sheet_text[:6000]}"
            )
            data = self.groq.extract_json(
                system_prompt=_PHASE2_SYSTEM,
                user_content=phase2_input,
            )
            logger.info(f"Phase 2 done: style={data.get('style_code')}, "
                        f"total_qty={data.get('total_qty')}, "
                        f"colors={len(data.get('colors', []))}")

            return {"success": True, "layout": layout, "data": data, "error": None}

        except Exception as e:
            logger.error(f"FormatUnderstander error: {e}")
            return {"success": False, "layout": {}, "data": {}, "error": str(e)}

    def understand_layout_only(self, text_repr: str, sample_rows: int = 40) -> Dict[str, Any]:
        """Chỉ chạy Phase 1 — dùng khi chỉ cần biết cấu trúc file."""
        lines = text_repr.splitlines()
        sample = "\n".join(lines[:sample_rows * 3])
        try:
            return self.groq.extract_json(
                system_prompt=_PHASE1_SYSTEM,
                user_content=f"Phân tích cấu trúc layout:\n\n{sample}",
            )
        except Exception as e:
            logger.error(f"Phase 1 only error: {e}")
            return {}

    def _get_sheet_text(self, structured: Dict[str, Any], sheet_name: str) -> Optional[str]:
        """Lấy text_repr của một sheet cụ thể từ structured data."""
        sheets = structured.get("structured", [])
        for sheet in sheets:
            if sheet.get("name") == sheet_name:
                rows = sheet.get("rows", [])
                lines = [f"=== Sheet: {sheet_name} ==="]
                for row in rows:
                    cells = row.get("cells", [])
                    cell_strs = [f"{c['col_letter']}={c['value']}" for c in cells]
                    lines.append(f"Row{row['row']:4d}: {' | '.join(cell_strs)}")
                return "\n".join(lines)
        return None
