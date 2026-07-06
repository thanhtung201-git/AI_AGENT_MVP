import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from backend.config.settings import settings

logger = logging.getLogger(__name__)


def send_trimlist_email(
    to_email: str,
    subject: str,
    body: str,
    attachment_path: str = None,
) -> None:
    """
    Gửi email qua Gmail SMTP với file đính kèm tuỳ chọn.
    Raises Exception nếu gửi thất bại.
    """
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        raise ValueError("Chưa cấu hình GMAIL_USER hoặc GMAIL_APP_PASSWORD trong .env")

    msg = MIMEMultipart()
    msg["From"]    = settings.GMAIL_USER
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html", "utf-8"))

    if attachment_path and Path(attachment_path).exists():
        filename = Path(attachment_path).name
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
        server.sendmail(settings.GMAIL_USER, to_email, msg.as_string())

    logger.info(f"Email sent to {to_email} | subject: {subject}")
