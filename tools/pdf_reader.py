"""
pdf_reader.py — Đọc file PO dạng PDF
Dùng pdfplumber kết hợp pypdf để trích xuất text, bảng biểu và dữ liệu ô Form (Interactive Fields)

Cài đặt: pip install pdfplumber pypdf
"""

import pdfplumber
from pypdf import PdfReader as PyPdfReader
import logging

logger = logging.getLogger(__name__)


def read_pdf(file_path: str) -> dict:
    """
    Đọc toàn bộ nội dung file PDF.
    Tự động trích xuất cả text thường, bảng biểu (table) và dữ liệu ô Form điền sẵn.

    Args:
        file_path (str): Đường dẫn file PDF

    Returns:
        dict: {
            "success": True/False,
            "text":    Toàn bộ nội dung text đã bóc tách,
            "format":  "pdf",
            "pages":   Số trang,
            "error":   Lỗi nếu có
        }
    """
    try:
        full_text = []
        total_pages = 0

        # ── 1. Đọc văn bản thô và bảng biểu bằng pdfplumber ──
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"Đang đọc PDF: {file_path} ({total_pages} trang)")

            for i, page in enumerate(pdf.pages):
                # Sử dụng layout=True để giữ nguyên cấu trúc vị trí văn bản
                page_text = page.extract_text(layout=True)
                if page_text:
                    full_text.append(f"--- Trang {i+1} ---")
                    full_text.append(page_text)

                # Extract bảng biểu (quan trọng với PO có size chart)
                tables = page.extract_tables()
                if tables:
                    for t_idx, table in enumerate(tables):
                        full_text.append(f"[Bảng {t_idx+1} - Trang {i+1}]")
                        for row in table:
                            clean_row = [str(cell).strip() if cell else "" for cell in row]
                            full_text.append("\t".join(clean_row))

        # ── 2. Đọc bổ sung dữ liệu từ các ô điền Form (AcroForm) bằng pypdf ──
        try:
            pypdf_reader = PyPdfReader(file_path)
            fields = pypdf_reader.get_fields()
            if fields:
                full_text.append("\n--- DỮ LIỆU TỪ Ô FORM ĐIỀN SẴN ---")
                for field_name, field_data in fields.items():
                    # '/V' đại diện cho Value (Giá trị được điền trong ô)
                    if field_data and '/V' in field_data and field_data['/V']:
                        val = str(field_data['/V']).strip()
                        # Làm sạch tên trường (loại bỏ các ký tự thừa nếu có)
                        clean_name = field_name.split('.')[-1].replace('_', ' ').title()
                        full_text.append(f"{clean_name}: {val}")
        except Exception as form_e:
            logger.warning(f"Không thể trích xuất form điền sẵn: {form_e}")

        # Gộp kết quả
        result_text = "\n".join(full_text).strip()

        if not result_text:
            return {
                "success": False,
                "text": "",
                "format": "pdf",
                "pages": total_pages,
                "error": "PDF không có dữ liệu text (có thể là file scan hoặc lỗi định dạng)."
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


# ── Chạy thử trực tiếp ──
if __name__ == "__main__":
    result = read_pdf("sample_data/test_po.pdf")
    if result["success"]:
        print(result["text"])
    else:
        print(f"Lỗi: {result['error']}")