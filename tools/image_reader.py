"""
image_reader.py — Đọc file ảnh PO (.jpg, .jpeg, .png, .bmp, .tiff, .webp)
Dùng Groq Vision API để trích xuất text từ ảnh (không cần Tesseract/OCR cục bộ)
"""

import base64
import logging
from pathlib import Path
from PIL import Image
import io

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def read_image(file_path: str) -> dict:
    try:
        path = Path(file_path)
        if path.suffix.lower() not in SUPPORTED_EXTS:
            return {"success": False, "text": "", "format": "image",
                    "error": f"Định dạng ảnh không hỗ trợ: {path.suffix}"}

        logger.info(f"Đang đọc ảnh: {file_path}")

        # Chuẩn hóa ảnh về JPEG để gửi API
        img = Image.open(file_path).convert("RGB")

        # Resize nếu quá lớn (Groq giới hạn ~20MB)
        max_size = (2048, 2048)
        img.thumbnail(max_size, Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        text = _call_groq_vision(img_b64)

        if not text:
            return {"success": False, "text": "", "format": "image",
                    "error": "Groq Vision không trích xuất được text từ ảnh."}

        return {"success": True, "text": text, "format": "image", "error": None}

    except FileNotFoundError:
        return {"success": False, "text": "", "format": "image",
                "error": f"Không tìm thấy file: {file_path}"}
    except Exception as e:
        logger.error(f"Lỗi đọc ảnh {file_path}: {e}")
        return {"success": False, "text": "", "format": "image",
                "error": f"Lỗi khi đọc ảnh: {str(e)}"}


def _call_groq_vision(img_b64: str) -> str:
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
                            "Đây là hình ảnh một Purchase Order (PO) hoặc đơn đặt hàng. "
                            "Hãy trích xuất TOÀN BỘ nội dung text trong ảnh, "
                            "giữ nguyên cấu trúc bảng, nhãn và giá trị. "
                            "Không giải thích, chỉ trả về text thuần."
                        ),
                    },
                ],
            }
        ],
        max_tokens=4096,
    )

    return response.choices[0].message.content.strip()
