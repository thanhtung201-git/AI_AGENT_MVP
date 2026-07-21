"""
POST /api/task-b/run      — Tech Pack + Trim Master + Email → Trimlist
GET  /api/task-b/download/{token} — Download Excel
"""
import os
import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)
router = APIRouter()
_db = SupabaseClient()

UPLOAD_DIR = "sample_data/uploads/task_b"
OUTPUT_DIR = "sample_data/trimlist"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def _save_upload(file: UploadFile, prefix: str) -> str:
    from datetime import datetime
    ext = os.path.splitext(file.filename)[-1].lower()
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(UPLOAD_DIR, f"{prefix}_{ts}{ext}")
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    return path


@router.post("/run")
async def run_task_b(
    techpack_file:    UploadFile = File(...),
    master_trim_file: Optional[UploadFile] = File(None),
    email_note:       str = Form(""),
    garment_type:     str = Form(""),
    buyer_code:       str = Form(""),
    branch:           str = Form(""),
    branch_confirmed: str = Form(""),
    po_number:        str = Form(""),
    style_code:       str = Form(""),
    style_name:       str = Form(""),
    buyer:            str = Form(""),
    order_qty:        str = Form("0"),
    season:           str = Form(""),
    factory:          str = Form(""),
):
    """Upload Tech Pack (+ optional Trim Master + email note) → tạo Trimlist đầy đủ."""
    # Validate Tech Pack
    ext = os.path.splitext(techpack_file.filename)[-1].lower()
    if ext not in (".pdf", ".xlsx", ".xls", ".docx"):
        raise HTTPException(400, "Tech Pack: chỉ hỗ trợ PDF, Excel, Word")

    # Lưu files
    techpack_path = await _save_upload(techpack_file, "techpack")
    master_path: Optional[str] = None
    if master_trim_file and master_trim_file.filename:
        ext2 = os.path.splitext(master_trim_file.filename)[-1].lower()
        if ext2 not in (".xlsx", ".xls"):
            raise HTTPException(400, "Trim Master: chỉ hỗ trợ Excel")
        master_path = await _save_upload(master_trim_file, "master")

    order_qty_int = 0
    try:
        order_qty_int = int(order_qty) if order_qty else 0
    except ValueError:
        pass

    meta = {
        "po_number":   po_number,
        "style_code":  style_code,
        "style_name":  style_name,
        "buyer":       buyer,
        "order_qty":   f"{order_qty_int:,} pcs" if order_qty_int else "",
        "order_qty_raw": order_qty_int,
        "season":      season,
        "factory":     factory,
    }

    from backend.services.task_b_service import TaskBService
    service = TaskBService()
    result  = service.run(
        techpack_path=techpack_path,
        master_trim_path=master_path,
        email_note=email_note,
        garment_type=garment_type,
        buyer_code=buyer_code,
        branch=branch,
        branch_confirmed=str(branch_confirmed).lower() in ("1", "true", "yes"),
        meta=meta,
    )

    if not result.get("success"):
        # 422 = user data issue (bad PDF, empty extraction), not server error
        raise HTTPException(422, result.get("error") or "Task B thất bại")

    # Record a compact summary so the dashboard can show trends.
    try:
        from backend.services.run_history import log_run, summarize_task_b
        log_run(summarize_task_b(result, meta))
    except Exception as e:
        logger.warning(f"Task B: run history log skipped ({e})")

    # Deep-link: expose the source files so the UI can open them to verify a value.
    result["sources"] = {
        "techpack": os.path.basename(techpack_path),
        "master":   os.path.basename(master_path) if master_path else None,
    }
    return result


@router.post("/detect-branch")
async def detect_branch(techpack_file: UploadFile = File(...)):
    """
    Step 1 (auto part): read the Tech Pack and infer the garment branch
    (gender × construction) so the UI can pre-fill it for a 1-click confirm.
    Returns the inferred branch + confidence + the list of valid branches.
    """
    from backend.trimlist.branch_detector import BranchDetector, GENDERS, CONSTRUCTIONS

    ext = os.path.splitext(techpack_file.filename or "")[-1].lower()
    if ext not in (".pdf", ".xlsx", ".xls", ".docx"):
        raise HTTPException(400, "Tech Pack: chỉ hỗ trợ PDF, Excel, Word")

    path = await _save_upload(techpack_file, "branchdetect")
    try:
        from tools.reader import read_file
        r = read_file(path)
        text = r.get("text") or "" if r.get("success") else ""
    except Exception as e:
        raise HTTPException(422, f"Không đọc được Tech Pack: {e}")

    info = BranchDetector().detect(text)
    options = [f"{g} {c}" for g in GENDERS for c in CONSTRUCTIONS]
    return {"success": True, "branch": info, "options": options}


class TaskBHistoryEntry(BaseModel):
    token:      str                       # = excel_token
    status:     str = "success"           # success | partial | error
    file_name:  Optional[str] = None      # tên file Tech Pack
    po_number:  Optional[str] = None
    style_code: Optional[str] = None
    qty:        Optional[int] = 0         # order qty
    item_count: Optional[int] = 0         # số trim item
    warning:    Optional[str] = None
    error:      Optional[str] = None


@router.get("/history")
def task_b_history(limit: int = 50):
    """Danh sách các lần tạo Trimlist (mới nhất trước)."""
    return {"success": True, "data": _db.task_b_history_get(limit=limit)}


@router.post("/history")
def task_b_history_save(entry: TaskBHistoryEntry):
    """Lưu một lần tạo Trimlist."""
    return {"success": _db.task_b_history_upsert(entry.model_dump())}


@router.get("/source/{filename}")
def open_source(filename: str):
    """Serve an uploaded source file (Tech Pack / Trim Master) so the user can jump
    to a value's exact location. Restricted to files in the Task B upload dir."""
    safe = os.path.basename(filename)   # block path traversal
    path = os.path.join(UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(404, "File nguồn không tồn tại")
    ext = os.path.splitext(safe)[1].lower()
    media = {
        ".pdf":  "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls":  "application/vnd.ms-excel",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media, filename=safe)


def _find_trimlist_path(token: str) -> Optional[str]:
    """Định vị file Trimlist Excel của một token (Task B lưu dạng trimlist_v2_*)."""
    for candidate in [f"trimlist_v2_{token}.xlsx", f"trimlist_taskb_{token}.xlsx"]:
        path = os.path.join(OUTPUT_DIR, candidate)
        if os.path.exists(path):
            return path
    return None


@router.get("/download/{token}")
def download_trimlist(token: str):
    path = _find_trimlist_path(token)
    if path:
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"Trimlist_{token}.xlsx",
        )
    raise HTTPException(404, f"File trimlist_{token}.xlsx không tồn tại")


@router.get("/pdf/{token}")
def trimlist_pdf(token: str):
    """Xuất Trimlist của Task B sang PDF (giống tab Tạo Trim List)."""
    xlsx = _find_trimlist_path(token)
    if not xlsx:
        raise HTTPException(404, "File Trimlist không tồn tại")
    from backend.utils.xlsx_pdf import xlsx_to_pdf
    pdf_path = os.path.join(OUTPUT_DIR, f"trimlist_{token}.pdf")
    try:
        xlsx_to_pdf(xlsx, pdf_path, title="TRIM LIST")
    except Exception as e:
        raise HTTPException(500, f"Tạo PDF thất bại: {e}")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"Trimlist_{token}.pdf")


class SendTaskBEmail(BaseModel):
    token:      str
    to_email:   str
    po_number:  str = ""
    style_code: str = ""
    qty:        int = 0
    item_count: int = 0


@router.post("/send-email")
def task_b_send_email(body: SendTaskBEmail):
    """Gửi Trimlist Excel của Task B qua Gmail."""
    xlsx = _find_trimlist_path(body.token)
    if not xlsx:
        raise HTTPException(404, "File Trimlist không tồn tại")
    from backend.utils.email_sender import send_trimlist_email

    subject = f"[MCNA] Trim List — PO: {body.po_number or body.token}"
    html_body = f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
  <p>Kính gửi,</p>
  <p>Vui lòng xem file <strong>Trim List</strong> đính kèm.</p>
  <table style="border-collapse: collapse; margin: 16px 0;">
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">PO Number:</td><td><strong>{body.po_number or "—"}</strong></td></tr>
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Style Code:</td><td><strong>{body.style_code or "—"}</strong></td></tr>
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Order Qty:</td><td><strong>{body.qty:,} pcs</strong></td></tr>
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Số loại trim:</td><td><strong>{body.item_count}</strong></td></tr>
  </table>
  <p style="color: #999; font-size: 12px;">Email được gửi tự động từ hệ thống AI Agent — MCNA Garment</p>
</div>
"""
    try:
        send_trimlist_email(to_email=body.to_email, subject=subject, body=html_body, attachment_path=xlsx)
    except Exception as e:
        raise HTTPException(500, f"Gửi email thất bại: {e}")
    return {"status": "success", "message": f"Đã gửi Trim List đến {body.to_email}"}


class SendTaskBTelegram(BaseModel):
    token:      str
    chat_id:    str = ""
    po_number:  str = ""
    style_code: str = ""
    qty:        int = 0
    item_count: int = 0


@router.post("/send-telegram")
def task_b_send_telegram(body: SendTaskBTelegram):
    """Gửi Trimlist Excel của Task B qua Telegram."""
    xlsx = _find_trimlist_path(body.token)
    if not xlsx:
        raise HTTPException(404, "File Trimlist không tồn tại")
    from backend.utils.telegram_sender import send_telegram_file
    from backend.config.settings import settings

    chat_id = body.chat_id or settings.TELEGRAM_DEFAULT_CHAT_ID
    if not chat_id:
        raise HTTPException(400, "Chưa có chat_id (đặt TELEGRAM_DEFAULT_CHAT_ID trong .env)")

    caption = (
        f"📋 <b>Trim List</b>\n"
        f"PO: <b>{body.po_number or '—'}</b>\n"
        f"Style: <b>{body.style_code or '—'}</b>\n"
        f"Qty: <b>{body.qty:,} pcs</b>\n"
        f"Số loại trim: <b>{body.item_count}</b>\n"
        f"<i>MCNA Garment — AI Agent</i>"
    )
    try:
        send_telegram_file(chat_id=chat_id, file_path=xlsx, caption=caption)
    except Exception as e:
        raise HTTPException(500, f"Gửi Telegram thất bại: {e}")
    return {"status": "success", "message": "Đã gửi Trim List qua Telegram"}
