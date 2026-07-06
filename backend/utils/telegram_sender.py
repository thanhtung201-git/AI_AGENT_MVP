import logging
import requests
from pathlib import Path
from backend.config.settings import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def send_telegram_file(
    chat_id: str,
    file_path: str,
    caption: str = "",
) -> None:
    """
    Gửi file Excel qua Telegram bot.
    Raises Exception nếu thất bại.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError("Chưa cấu hình TELEGRAM_BOT_TOKEN trong .env")

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")

    base_url = TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN)

    with open(path, "rb") as f:
        resp = requests.post(
            f"{base_url}/sendDocument",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"document": (path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=30,
        )

    if not resp.ok:
        raise RuntimeError(f"Telegram API lỗi {resp.status_code}: {resp.text}")

    logger.info(f"Telegram file sent to chat_id={chat_id}: {path.name}")


def send_telegram_message(chat_id: str, text: str) -> None:
    """Gửi tin nhắn text qua Telegram."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise ValueError("Chưa cấu hình TELEGRAM_BOT_TOKEN trong .env")

    base_url = TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN)
    resp = requests.post(
        f"{base_url}/sendMessage",
        data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Telegram API lỗi {resp.status_code}: {resp.text}")
