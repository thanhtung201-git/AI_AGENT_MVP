"""
pdf_reader.py — Đọc file PO dạng PDF
Dùng pdfplumber để extract text và bảng biểu

Cài đặt: pip install pdfplumber
"""

import pdfplumber
import logging

logger = logging.getLogger(__name__)


def read_pdf(file_path: str) -> dict:
    """
    Đọc toàn bộ nội dung file PDF.
    Tự động extract cả text thường lẫn bảng biểu (table).

    Args:
        file_path (str): Đường dẫn file PDF

    Returns:
        dict: {
            "success": True/False,
            "text":    Toàn bộ nội dung text,
            "format":  "pdf",
            "pages":   Số trang,
            "error":   Lỗi nếu có
        }
    """
    try:
        full_text = []

        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"Đang đọc PDF: {file_path} ({total_pages} trang)")

            for i, page in enumerate(pdf.pages):

                # ── 1. Extract text thường ──
                page_text = page.extract_text()
                if page_text:
                    full_text.append(f"--- Trang {i+1} ---")
                    full_text.append(page_text)

                # ── 2. Extract bảng biểu (quan trọng với PO có size chart) ──
                tables = page.extract_tables()
                if tables:
                    for t_idx, table in enumerate(tables):
                        full_text.append(f"[Bảng {t_idx+1} - Trang {i+1}]")
                        for row in table:
                            # Lọc ô None, join bằng tab để dễ đọc
                            clean_row = [str(cell).strip() if cell else "" for cell in row]
                            full_text.append("\t".join(clean_row))

        result_text = "\n".join(full_text).strip()

        if not result_text:
            # PDF có thể là scan (ảnh) — cần OCR
            return {
                "success": False,
                "text": "",
                "format": "pdf",
                "pages": total_pages,
                "error": "PDF không có text (có thể là file scan). Cần dùng OCR."
            }

        return {
            "success": True,
            "text": result_text,
            "format": "pdf",
            "pages": total_pages,
            "error": None
        }

    except FileNotFoundError:
        return {
            "success": False,
            "text": "",
            "format": "pdf",
            "pages": 0,
            "error": f"Không tìm thấy file: {file_path}"
        }

    except Exception as e:
        logger.error(f"Lỗi đọc PDF {file_path}: {e}")
        return {
            "success": False,
            "text": "",
            "format": "pdf",
            "pages": 0,
            "error": f"Lỗi khi đọc PDF: {str(e)}"
        }


# ── Chạy thử ──
if __name__ == "__main__":
    result = read_pdf("sample_data/test_po.pdf")
    print(result)