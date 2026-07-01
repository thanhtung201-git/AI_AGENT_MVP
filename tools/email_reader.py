"""
email_reader.py — Đọc file email PO (.eml, .msg)
- .eml: dùng thư viện email built-in của Python
- .msg: dùng extract-msg (pip install extract-msg)
Trích xuất nội dung text + thông tin người gửi/nhận/tiêu đề
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_email(file_path: str) -> dict:
    ext = Path(file_path).suffix.lower()
    if ext == ".eml":
        return _read_eml(file_path)
    elif ext == ".msg":
        return _read_msg(file_path)
    else:
        return {"success": False, "text": "", "format": "email",
                "error": f"Định dạng email không hỗ trợ: {ext}"}


def _read_eml(file_path: str) -> dict:
    import email as email_lib
    from email import policy

    try:
        logger.info(f"Đang đọc email .eml: {file_path}")
        with open(file_path, "rb") as f:
            msg = email_lib.message_from_binary_file(f, policy=policy.default)

        parts = []

        # Header thông tin
        parts.append(f"From   : {msg.get('From', '')}")
        parts.append(f"To     : {msg.get('To', '')}")
        parts.append(f"Subject: {msg.get('Subject', '')}")
        parts.append(f"Date   : {msg.get('Date', '')}")
        parts.append("")

        # Body text
        body = _extract_eml_body(msg)
        if body:
            parts.append("--- NỘI DUNG EMAIL ---")
            parts.append(body)

        # Danh sách file đính kèm (không đọc nội dung attachment ở đây)
        attachments = _list_eml_attachments(msg)
        if attachments:
            parts.append("")
            parts.append("--- FILE ĐÍNH KÈM ---")
            for att in attachments:
                parts.append(f"  - {att}")

        result_text = "\n".join(parts).strip()
        return {"success": True, "text": result_text, "format": "email",
                "attachments": attachments, "error": None}

    except FileNotFoundError:
        return {"success": False, "text": "", "format": "email",
                "error": f"Không tìm thấy file: {file_path}"}
    except Exception as e:
        logger.error(f"Lỗi đọc .eml {file_path}: {e}")
        return {"success": False, "text": "", "format": "email",
                "error": f"Lỗi khi đọc email: {str(e)}"}


def _read_msg(file_path: str) -> dict:
    try:
        import extract_msg
    except ImportError:
        return {"success": False, "text": "", "format": "email",
                "error": "Thiếu thư viện extract-msg. Chạy: pip install extract-msg"}

    try:
        logger.info(f"Đang đọc email .msg: {file_path}")
        msg = extract_msg.Message(file_path)

        parts = []
        parts.append(f"From   : {msg.sender or ''}")
        parts.append(f"To     : {msg.to or ''}")
        parts.append(f"Subject: {msg.subject or ''}")
        parts.append(f"Date   : {msg.date or ''}")
        parts.append("")

        body = msg.body or ""
        if body.strip():
            parts.append("--- NỘI DUNG EMAIL ---")
            parts.append(body.strip())

        attachments = [att.longFilename or att.shortFilename or "unknown"
                       for att in msg.attachments]
        if attachments:
            parts.append("")
            parts.append("--- FILE ĐÍNH KÈM ---")
            for att in attachments:
                parts.append(f"  - {att}")

        msg.close()

        result_text = "\n".join(parts).strip()
        return {"success": True, "text": result_text, "format": "email",
                "attachments": attachments, "error": None}

    except FileNotFoundError:
        return {"success": False, "text": "", "format": "email",
                "error": f"Không tìm thấy file: {file_path}"}
    except Exception as e:
        logger.error(f"Lỗi đọc .msg {file_path}: {e}")
        return {"success": False, "text": "", "format": "email",
                "error": f"Lỗi khi đọc email: {str(e)}"}


def _extract_eml_body(msg) -> str:
    """Lấy phần text/plain hoặc text/html từ email."""
    body_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                body_parts.append(part.get_content())
    else:
        body_parts.append(msg.get_content())
    return "\n".join(body_parts).strip()


def _list_eml_attachments(msg) -> list:
    attachments = []
    for part in msg.walk():
        cd = str(part.get("Content-Disposition", ""))
        if "attachment" in cd:
            filename = part.get_filename() or "unknown"
            attachments.append(filename)
    return attachments
