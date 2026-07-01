"""
pdf_scan_reader.py — Đọc PDF scan (không có text layer)
Dùng pymupdf để render từng trang thành ảnh, sau đó gửi Groq Vision API
"""

import base64
import logging
import io
from pathlib import Path

import fitz  # pymupdf
from PIL import Image

logger = logging.getLogger(__name__)

# Nếu PDF có ít hơn ngưỡng này ký tự/trang → coi là scan
_MIN_CHARS_PER_PAGE = 50


def is_scanned_pdf(file_path: str) -> bool:
    """Kiểm tra PDF có phải là scan (không có text layer) không."""
    try:
        doc = fitz.open(file_path)
        total_chars = sum(len(page.get_text().strip()) for page in doc)
        avg = total_chars / max(len(doc), 1)
        doc.close()
        return avg < _MIN_CHARS_PER_PAGE
    except Exception:
        return False


def read_pdf_scan(file_path: str) -> dict:
    try:
        logger.info(f"Đang đọc PDF scan: {file_path}")
        doc = fitz.open(file_path)
        total_pages = len(doc)
        full_text = []

        for i, page in enumerate(doc):
            logger.info(f"  Xử lý trang {i+1}/{total_pages}...")

            # Render trang thành ảnh (150 DPI đủ để OCR, không quá nặng)
            mat = fitz.Matrix(150 / 72, 150 / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

            page_text = _call_groq_vision(img_b64, page_num=i + 1)
            if page_text:
                full_text.append(f"--- Trang {i+1} ---")
                full_text.append(page_text)

        doc.close()
        result_text = "\n".join(full_text).strip()

        if not result_text:
            return {"success": False, "text": "", "format": "pdf_scan",
                    "pages": total_pages,
                    "error": "Không trích xuất được text từ PDF scan."}

        return {"success": True, "text": result_text, "format": "pdf_scan",
                "pages": total_pages, "error": None}

    except FileNotFoundError:
        return {"success": False, "text": "", "format": "pdf_scan",
                "pages": 0, "error": f"Không tìm thấy file: {file_path}"}
    except Exception as e:
        logger.error(f"Lỗi đọc PDF scan {file_path}: {e}")
        return {"success": False, "text": "", "format": "pdf_scan",
                "pages": 0, "error": f"Lỗi khi đọc PDF scan: {str(e)}"}


def _call_groq_vision(img_b64: str, page_num: int = 1) -> str:
    from groq import Groq
    from backend.config.settings import settings

    client = Groq(api_key=settings.GROQ_API_KEY)

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Đây là trang {page_num} của một Purchase Order (PO) dạng scan. "
                            "Hãy trích xuất TOÀN BỘ nội dung text trong ảnh, "
                            "giữ nguyên cấu trúc bảng, nhãn cột và giá trị. "
                            "Không giải thích, chỉ trả về text thuần."
                        ),
                    },
                ],
            }
        ],
        max_tokens=4096,
    )

    return response.choices[0].message.content.strip()
