"""
reader.py — File router chính
Nhận đường dẫn file bất kỳ → tự detect định dạng → gọi đúng reader

Dự án: Tesselation AI Agent
Tác giả: NTT / TTK
"""

import os
from pathlib import Path

# Import 3 reader con
from tools.pdf_reader   import read_pdf
from tools.excel_reader import read_excel
from tools.word_reader  import read_word


def read_file(file_path: str) -> dict:
    """
    Hàm tổng hợp: đọc file PO bất kỳ định dạng.

    Args:
        file_path (str): Đường dẫn đến file PO (PDF / Excel / Word)

    Returns:
        dict: {
            "success": True/False,
            "text":    Nội dung text trích xuất được,
            "format":  "pdf" | "excel" | "word",
            "error":   Thông báo lỗi nếu có
        }

    Ví dụ:
        result = read_file("sample_data/PO_buyer_A.pdf")
        if result["success"]:
            print(result["text"])
    """
    path = Path(file_path)

    # Kiểm tra file tồn tại
    if not path.exists():
        return {
            "success": False,
            "text": "",
            "format": None,
            "error": f"Không tìm thấy file: {file_path}"
        }

    ext = path.suffix.lower()

    # ── Routing theo extension ──
    if ext == ".pdf":
        return read_pdf(file_path)

    elif ext in [".xlsx", ".xls", ".xlsm"]:
        return read_excel(file_path)

    elif ext in [".docx", ".doc"]:
        return read_word(file_path)

    else:
        return {
            "success": False,
            "text": "",
            "format": None,
            "error": f"Định dạng không hỗ trợ: {ext}. Chỉ nhận PDF, Excel, Word."
        }


# ── Chạy thử trực tiếp ──
if __name__ == "__main__":
    import sys

    test_file = sys.argv[1] if len(sys.argv) > 1 else "sample_data/test_po.pdf"
    result = read_file(test_file)

    if result["success"]:
        print(f"✅ Đọc thành công | Định dạng: {result['format']}")
        print(f"📄 Nội dung ({len(result['text'])} ký tự):")
        print(result["text"][:500])  # In 500 ký tự đầu
    else:
        print(f"❌ Lỗi: {result['error']}")