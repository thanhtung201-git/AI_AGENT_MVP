"""
POST /api/task-a/run          — PO → Batch GO → read back GO → Compare (round-trip QA)
GET  /api/task-a/download/{f}  — download any generated output file

User uploads ONLY the PO. The system generates the Batch GO Upload, reads it back
as GO Information, and compares GO ↔ PO. Fully LLM-driven, no customer-specific logic.
"""
import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)
router = APIRouter()
_db = SupabaseClient()

_BASE       = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_UPLOAD_DIR = os.path.join(_BASE, "uploads", "task_a")
_OUTPUT_DIR = os.path.join(_BASE, "sample_data", "go_compare")
os.makedirs(_UPLOAD_DIR, exist_ok=True)
os.makedirs(_OUTPUT_DIR, exist_ok=True)

_MEDIA = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
}


@router.post("/generate")
async def task_a_generate(po_file: UploadFile = File(...)):
    """
    STEP 1 — Upload PO → generate the Batch GO Upload. No comparison yet.
    Output: { success, token, po, batch_go_token }
    """
    from backend.go_compare.pipeline import GOComparePipeline

    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    po_path = os.path.join(_UPLOAD_DIR, f"{ts}_po_{po_file.filename}")
    with open(po_path, "wb") as f:
        f.write(await po_file.read())

    try:
        result = GOComparePipeline().generate_batch_go(po_path, output_dir=_OUTPUT_DIR)
    except Exception as e:
        logger.exception("Task A generate crashed")
        return {"success": False, "error": str(e)}

    if not result.get("success"):
        return {"success": False, "error": result.get("error")}

    return {
        "success":        True,
        "token":          result["token"],
        "po":             result["po"],
        "validation":     result.get("validation"),
        "batch_go_token": os.path.basename(result["batch_go_path"]),
    }


@router.post("/compare")
async def task_a_compare(
    token:   str = Form(...),
    go_file: UploadFile = File(None),
):
    """
    STEP 2 — Compare the PO (from STEP 1's token) against a GO.
    If go_file is provided → PO ↔ real GO. Otherwise → round-trip self-check
    against the Batch GO generated in STEP 1.
    Output: { success, go_source, compare, po, go, report_token, alerts_token }
    """
    from backend.go_compare.pipeline import GOComparePipeline

    go_path = None
    if go_file and go_file.filename:
        go_path = os.path.join(_UPLOAD_DIR, f"{token}_go_{go_file.filename}")
        with open(go_path, "wb") as f:
            f.write(await go_file.read())

    try:
        result = GOComparePipeline().run_compare(token, output_dir=_OUTPUT_DIR, go_file_path=go_path)
    except Exception as e:
        logger.exception("Task A compare crashed")
        return {"success": False, "error": str(e)}

    if not result.get("success"):
        return {"success": False, "error": result.get("error")}

    # Record a compact summary so the dashboard can show trends.
    try:
        from backend.services.run_history import log_run, summarize_task_a
        log_run(summarize_task_a(result))
    except Exception as e:
        logger.warning(f"Task A: run history log skipped ({e})")

    return {
        "success":      True,
        "token":        result["token"],
        "go_source":    result.get("go_source", "generated"),
        "compare":      result["compare"],
        "po":           result["po"],
        "go":           result["go"],
        "report_token": os.path.basename(result["report_path"]),
        "alerts_token": os.path.basename(result["alerts_path"]),
    }


class TaskAHistoryEntry(BaseModel):
    token:          str
    status:         str = "partial"      # success | partial | error
    file_name:      Optional[str] = None
    po_number:      Optional[str] = None
    style_code:     Optional[str] = None
    qty:            Optional[int] = 0
    compared:       Optional[int] = 0    # số dòng đã so sánh
    go_source:      Optional[str] = None # 'uploaded' | 'generated'
    batch_go_token: Optional[str] = None
    report_token:   Optional[str] = None
    alerts_token:   Optional[str] = None
    warning:        Optional[str] = None
    error:          Optional[str] = None


@router.get("/history")
def task_a_history(limit: int = 50):
    """Danh sách các lần chạy PO ↔ GO (mới nhất trước)."""
    return {"success": True, "data": _db.task_a_history_get(limit=limit)}


@router.post("/history")
def task_a_history_save(entry: TaskAHistoryEntry):
    """Lưu/cập nhật một lần chạy. Gộp theo token (generate + compare cùng dòng)."""
    return {"success": _db.task_a_history_upsert(entry.model_dump())}


class SendTaskAEmail(BaseModel):
    filename:   str          # batch_go_token (tên file Batch GO trong go_compare)
    to_email:   str
    po_number:  str = ""
    style_code: str = ""
    qty:        int = 0


@router.post("/send-email")
def task_a_send_email(body: SendTaskAEmail):
    """Gửi file Batch GO Excel qua Gmail."""
    path = os.path.join(_OUTPUT_DIR, os.path.basename(body.filename))
    if not os.path.isfile(path):
        raise HTTPException(404, "File Batch GO không tồn tại")
    from backend.utils.email_sender import send_trimlist_email

    subject = f"[MCNA] Batch GO — PO: {body.po_number or body.filename}"
    html_body = f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
  <p>Kính gửi,</p>
  <p>Vui lòng xem file <strong>Batch GO Upload</strong> đính kèm.</p>
  <table style="border-collapse: collapse; margin: 16px 0;">
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">PO Number:</td><td><strong>{body.po_number or "—"}</strong></td></tr>
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Style Code:</td><td><strong>{body.style_code or "—"}</strong></td></tr>
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Total Qty:</td><td><strong>{body.qty:,} pcs</strong></td></tr>
  </table>
  <p style="color: #999; font-size: 12px;">Email được gửi tự động từ hệ thống AI Agent — MCNA Garment</p>
</div>
"""
    try:
        send_trimlist_email(to_email=body.to_email, subject=subject, body=html_body, attachment_path=path)
    except Exception as e:
        raise HTTPException(500, f"Gửi email thất bại: {e}")
    return {"status": "success", "message": f"Đã gửi Batch GO đến {body.to_email}"}


class SendTaskATelegram(BaseModel):
    filename:   str
    chat_id:    str = ""
    po_number:  str = ""
    style_code: str = ""
    qty:        int = 0


@router.post("/send-telegram")
def task_a_send_telegram(body: SendTaskATelegram):
    """Gửi file Batch GO Excel qua Telegram."""
    path = os.path.join(_OUTPUT_DIR, os.path.basename(body.filename))
    if not os.path.isfile(path):
        raise HTTPException(404, "File Batch GO không tồn tại")
    from backend.utils.telegram_sender import send_telegram_file
    from backend.config.settings import settings

    chat_id = body.chat_id or settings.TELEGRAM_DEFAULT_CHAT_ID
    if not chat_id:
        raise HTTPException(400, "Chưa có chat_id (đặt TELEGRAM_DEFAULT_CHAT_ID trong .env)")

    caption = (
        f"📦 <b>Batch GO Upload</b>\n"
        f"PO: <b>{body.po_number or '—'}</b>\n"
        f"Style: <b>{body.style_code or '—'}</b>\n"
        f"Qty: <b>{body.qty:,} pcs</b>\n"
        f"<i>MCNA Garment — AI Agent</i>"
    )
    try:
        send_telegram_file(chat_id=chat_id, file_path=path, caption=caption)
    except Exception as e:
        raise HTTPException(500, f"Gửi Telegram thất bại: {e}")
    return {"status": "success", "message": "Đã gửi Batch GO qua Telegram"}


@router.get("/download/{filename}")
async def download_output(filename: str):
    """Download any generated output (Batch GO, Compare Report, Alerts JSON)."""
    path = os.path.join(_OUTPUT_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File không tìm thấy")
    ext = os.path.splitext(filename)[1].lower()
    return FileResponse(
        path,
        media_type=_MEDIA.get(ext, "application/octet-stream"),
        filename=filename,
    )
