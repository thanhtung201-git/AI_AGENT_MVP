"""
tools/__init__.py
Export các hàm chính để import gọn hơn từ bên ngoài

Cách dùng:
    from tools import read_file          # Import hàm tổng hợp
    from tools import read_pdf           # Import riêng từng reader
"""

from tools.reader       import read_file
from tools.pdf_reader   import read_pdf
from tools.excel_reader import read_excel
from tools.word_reader  import read_word

__all__ = [
    "read_file",    # Dùng cái này là đủ cho 99% trường hợp
    "read_pdf",
    "read_excel",
    "read_word",
]