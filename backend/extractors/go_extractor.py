"""
go_extractor.py — Đọc file "GO Information" Excel của Hazzys.

File GO Information chứa: GO number, style, colors, qty, shipment date,
destination, factory, buyer reference... — layout không cố định.

Dùng read_excel_structured() + Groq 1-phase (layout thường đơn giản hơn HZSH).

Output:
  {
    "go_number":    "S26M01565",
    "style_no":     "HZSH6C331",
    "season":       "26 F/W",
    "buyer":        "HAZZYS",
    "factory":      "MCNA",
    "issue_date":   "2026-03-01",
    "ship_date":    "2026-07-15",
    "colors": [
      {
        "color_code":  "N2",
        "color_name":  "NORMAL NAVY",
        "total_qty":   774,
        "sizes":       {"00S": 191, "00M": 283, ...},
        "destination": "LF"
      }
    ],
    "total_qty": 1274
  }
"""

import logging
from typing import Any, Dict, List

from tools.excel_reader import read_excel_structured
from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Bạn là chuyên gia đọc file GO Information (Garment Order) của Hazzys - ngành may mặc.

File GO Information chứa thông tin đơn hàng đã được xác nhận: GO number, style, màu sắc, số lượng, ngày giao hàng, destination, factory...

Hãy extract và trả về JSON:
{
  "go_number":   "...",
  "style_no":    "...",
  "season":      "...",
  "buyer":       "...",
  "factory":     "...",
  "issue_date":  "YYYY-MM-DD hoặc chuỗi gốc nếu không parse được",
  "ship_date":   "YYYY-MM-DD hoặc chuỗi gốc",
  "cancel_date": "YYYY-MM-DD hoặc chuỗi gốc hoặc null",
  "colors": [
    {
      "color_code":  "N2",
      "color_name":  "NORMAL NAVY",
      "total_qty":   774,
      "destination": "LF hoặc null",
      "sizes":       {"00S": 191, "00M": 283, "00L": 206}
    }
  ],
  "total_qty": 1274
}

Nếu không có thông tin size breakdown, để sizes = {}.
Nếu không tìm thấy một trường nào, để null.
Chỉ trả JSON thuần, không markdown."""


class GOExtractor:
    """Đọc file GO Information Excel và trả về GO data."""

    def __init__(self):
        self.groq = GroqClient()

    def extract(self, file_path: str) -> Dict[str, Any]:
        """
        Extract dữ liệu từ file GO Information.

        Returns:
            {"success": bool, "data": dict, "error": str|None}
        """
        logger.info(f"GOExtractor: đọc {file_path}")

        structured = read_excel_structured(file_path)
        if not structured["success"]:
            return {"success": False, "data": {}, "error": structured["error"]}

        text_repr = structured.get("text_repr", "")
        if not text_repr:
            return {"success": False, "data": {}, "error": "File không có dữ liệu"}

        try:
            data = self.groq.extract_json(
                system_prompt=_SYSTEM_PROMPT,
                user_content=f"Extract dữ liệu GO Information:\n\n{text_repr[:6000]}",
            )
            # Đảm bảo total_qty luôn có
            if "total_qty" not in data or not data["total_qty"]:
                data["total_qty"] = sum(
                    c.get("total_qty", 0) for c in data.get("colors", [])
                )
            logger.info(
                f"GOExtractor: go={data.get('go_number')}, "
                f"style={data.get('style_no')}, total_qty={data.get('total_qty')}"
            )
            return {"success": True, "data": data, "error": None}

        except Exception as e:
            logger.error(f"GOExtractor Groq error: {e}")
            return {"success": False, "data": {}, "error": str(e)}
