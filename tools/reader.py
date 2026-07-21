"""
reader.py — File router chính
Nhận đường dẫn file bất kỳ → tự detect định dạng → gọi đúng reader

Hỗ trợ:
  - PDF thường   : .pdf (có text layer)
  - PDF scan     : .pdf (ảnh chụp, dùng Groq Vision)
  - Excel        : .xlsx / .xls / .xlsm
  - Word         : .docx / .doc
  - Ảnh          : .jpg / .jpeg / .png / .bmp / .tiff / .webp
  - Email        : .eml / .msg

Dự án: Tesselation AI Agent
"""

from pathlib import Path

from tools.pdf_reader     import read_pdf
from tools.pdf_scan_reader import read_pdf_scan, is_scanned_pdf
from tools.excel_reader   import read_excel
from tools.word_reader    import read_word
from tools.image_reader   import read_image
from tools.email_reader   import read_email

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
_EXCEL_EXTS = {".xlsx", ".xls", ".xlsm"}
_WORD_EXTS  = {".docx", ".doc"}
_EMAIL_EXTS = {".eml", ".msg"}


def read_file(file_path: str) -> dict:
    """
    Đọc file PO bất kỳ định dạng, tự detect và gọi đúng reader.

    Returns:
        dict: {
            "success": True/False,
            "text":    Nội dung text trích xuất được,
            "format":  "pdf" | "pdf_scan" | "excel" | "word" | "image" | "email",
            "error":   Thông báo lỗi nếu có
        }
    """
    path = Path(file_path)

    if not path.exists():
        return {"success": False, "text": "", "format": None,
                "error": f"Không tìm thấy file: {file_path}"}

    ext = path.suffix.lower()

    if ext == ".pdf":
        # Tự phát hiện PDF scan hay PDF thường
        if is_scanned_pdf(file_path):
            return read_pdf_scan(file_path)
        return read_pdf(file_path)

    elif ext in _EXCEL_EXTS:
        from tools.excel_reader import read_excel_structured
        r = read_excel_structured(file_path)
        if r.get("success"):
            return {"success": True, "text": r["text_repr"],
                    "format": "excel_structured", "error": None}
        return read_excel(file_path)

    elif ext in _WORD_EXTS:
        return read_word(file_path)

    elif ext in _IMAGE_EXTS:
        return read_image(file_path)

    elif ext in _EMAIL_EXTS:
        return read_email(file_path)

    else:
        supported = "PDF, Excel, Word, Ảnh (jpg/png/bmp/tiff/webp), Email (eml/msg)"
        return {"success": False, "text": "", "format": None,
                "error": f"Định dạng không hỗ trợ: {ext}. Hỗ trợ: {supported}"}


# ── Chạy thử trực tiếp ──
if __name__ == "__main__":
    import sys

    test_file = sys.argv[1] if len(sys.argv) > 1 else "sample_data/test_po.pdf"
    result = read_file(test_file)

    if result["success"]:
        print(f"Đọc thành công | Định dạng: {result['format']}")
        print(f"Nội dung ({len(result['text'])} ký tự):")
        print(result["text"][:500])
    else:
        print(f"Lỗi: {result['error']}")
