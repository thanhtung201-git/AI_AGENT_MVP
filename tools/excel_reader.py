"""
excel_reader.py — Đọc file PO dạng Excel (.xlsx / .xls)
Dùng pandas để đọc, tự xử lý nhiều sheet

Cài đặt: pip install pandas openpyxl
"""

import pandas as pd
import logging

logger = logging.getLogger(__name__)


def read_excel(file_path: str) -> dict:
    """
    Đọc toàn bộ nội dung file Excel PO.
    Tự động đọc tất cả các sheet, convert về text để truyền vào LLM.

    Args:
        file_path (str): Đường dẫn file Excel (.xlsx / .xls)

    Returns:
        dict: {
            "success":  True/False,
            "text":     Nội dung text từ tất cả sheet,
            "format":   "excel",
            "sheets":   Danh sách tên sheet đã đọc,
            "error":    Lỗi nếu có
        }
    """
    try:
        # Đọc tất cả sheet trong file
        all_sheets = pd.read_excel(file_path, sheet_name=None, dtype=str)
        logger.info(f"Đang đọc Excel: {file_path} ({len(all_sheets)} sheet)")

        full_text = []
        sheet_names = list(all_sheets.keys())

        for sheet_name, df in all_sheets.items():

            # Bỏ qua sheet hoàn toàn trống
            if df.empty:
                continue

            full_text.append(f"=== Sheet: {sheet_name} ===")

            # ── Xử lý DataFrame ──
            # Xóa hàng/cột hoàn toàn trống
            df = df.dropna(how="all").dropna(axis=1, how="all")

            # Điền NaN bằng chuỗi rỗng
            df = df.fillna("")

            # Convert thành text dạng bảng (dễ đọc hơn cho LLM)
            sheet_text = df.to_string(index=False)
            full_text.append(sheet_text)
            full_text.append("")  # Dòng trống phân cách giữa các sheet

        result_text = "\n".join(full_text).strip()

        if not result_text:
            return {
                "success": False,
                "text": "",
                "format": "excel",
                "sheets": sheet_names,
                "error": "File Excel không có dữ liệu"
            }

        return {
            "success": True,
            "text": result_text,
            "format": "excel",
            "sheets": sheet_names,
            "error": None
        }

    except FileNotFoundError:
        return {
            "success": False,
            "text": "",
            "format": "excel",
            "sheets": [],
            "error": f"Không tìm thấy file: {file_path}"
        }

    except Exception as e:
        logger.error(f"Lỗi đọc Excel {file_path}: {e}")
        return {
            "success": False,
            "text": "",
            "format": "excel",
            "sheets": [],
            "error": f"Lỗi khi đọc Excel: {str(e)}"
        }


# ── Chạy thử ──
if __name__ == "__main__":
    result = read_excel("sample_data/test_po.xlsx")
    print(result)