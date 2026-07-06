"""
GET  /api/recap/sessions              — Danh sách trimlist sessions để chọn
POST /api/recap/aggregate             — Gom nhóm trim items từ nhiều sessions
GET  /api/recap/history               — Lịch sử các lần tổng hợp đã lưu
GET  /api/recap/download/{timestamp}  — Download Excel kết quả
"""
import os
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.database.supabase_client import SupabaseClient
from backend.exporters.recap_aggregate_exporter import RecapAggregateExporter
from backend.utils.email_sender import send_trimlist_email

logger = logging.getLogger(__name__)
router = APIRouter()

OUTPUT_DIR   = "sample_data/recap"
HISTORY_FILE = "sample_data/recap/.recap_history.json"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(entry: dict) -> None:
    history = _load_history()
    history.insert(0, entry)   # mới nhất lên đầu
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ── Schema ────────────────────────────────────────────────────────────────────

class AggregateRequest(BaseModel):
    session_ids: List[int]


class SendTelegramRequest(BaseModel):
    chat_id:     str = ""
    timestamp:   str
    po_numbers:  str = ""
    total_items: int = 0
    total_qty:   int = 0


@router.post("/send-telegram")
def send_recap_telegram(body: SendTelegramRequest):
    """Gửi file Recap Trim Excel qua Telegram."""
    from backend.utils.telegram_sender import send_telegram_file
    from backend.config.settings import settings

    excel_path = os.path.join(OUTPUT_DIR, f"recap_aggregate_{body.timestamp}.xlsx")
    if not os.path.exists(excel_path):
        raise HTTPException(404, "File Excel không tồn tại")

    chat_id = body.chat_id or settings.TELEGRAM_DEFAULT_CHAT_ID
    if not chat_id:
        raise HTTPException(400, "Chưa có chat_id")

    caption = (
        f"📊 <b>Recap Trim List</b>\n"
        f"PO: <b>{body.po_numbers or '—'}</b>\n"
        f"Số loại trim: <b>{body.total_items}</b>\n"
        f"Tổng qty: <b>{body.total_qty:,}</b>\n"
        f"<i>MCNA Garment — AI Agent</i>"
    )
    try:
        send_telegram_file(chat_id=chat_id, file_path=excel_path, caption=caption)
    except Exception as e:
        raise HTTPException(500, f"Gửi Telegram thất bại: {e}")

    return {"status": "success", "message": "Đã gửi Recap Trim qua Telegram"}


class SendEmailRequest(BaseModel):
    to_email: str
    timestamp: str
    po_numbers: str = ""
    total_items: int = 0
    total_qty: int = 0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/history")
def get_history():
    """Trả về lịch sử các lần tổng hợp trim đã lưu."""
    return {"history": _load_history()}


@router.get("/sessions")
def get_sessions(limit: int = 50):
    """Trả về danh sách trimlist sessions từ Supabase để frontend chọn."""
    db = SupabaseClient()
    if db.mock_mode:
        return {"sessions": [], "warning": "Supabase chưa kết nối"}
    sessions = db.get_trimlist_sessions(limit=limit)
    return {"sessions": sessions}


@router.post("/aggregate")
def aggregate_trim(body: AggregateRequest):
    """
    Nhận danh sách session_id → fetch trim_items → gom nhóm theo
    trim_item + spec + supplier → cộng dồn qty → trả về bảng tổng hợp.
    """
    if not body.session_ids:
        raise HTTPException(400, "Cần chọn ít nhất 1 trimlist")

    db = SupabaseClient()
    if db.mock_mode:
        raise HTTPException(503, "Supabase chưa kết nối")

    # Lấy thông tin sessions để build meta
    sessions_info = db.get_trimlist_sessions(limit=100)
    selected = {s["id"]: s for s in sessions_info if s["id"] in body.session_ids}
    if not selected:
        raise HTTPException(404, "Không tìm thấy sessions được chọn")

    # Lấy tất cả trim_items
    raw_items = db.get_trim_items_by_sessions(body.session_ids)
    if not raw_items:
        raise HTTPException(422, "Không có trim items trong các sessions được chọn")

    # Gom nhóm: key = (trim_item, spec, supplier)
    groups: dict = defaultdict(lambda: {
        "trim_item": "",
        "spec":      "",
        "supplier":  "",
        "unit":      "",
        "total_qty": 0,
        "po_list":   set(),
    })

    for item in raw_items:
        key = (
            (item.get("trim_item") or "").strip().lower(),
            (item.get("spec")      or "").strip().lower(),
            (item.get("supplier")  or "").strip().lower(),
        )
        g = groups[key]
        g["trim_item"] = item.get("trim_item") or g["trim_item"]
        g["spec"]      = item.get("spec")      or g["spec"]
        g["supplier"]  = item.get("supplier")  or g["supplier"]
        g["unit"]      = item.get("unit")      or g["unit"]
        g["total_qty"] += int(item.get("total_qty") or 0)
        if item.get("po_number"):
            g["po_list"].add(item["po_number"])

    # Chuyển thành list, sắp xếp theo trim_item
    aggregated = []
    for g in sorted(groups.values(), key=lambda x: (x["trim_item"], x["spec"])):
        aggregated.append({
            "trim_item":  g["trim_item"],
            "spec":       g["spec"],
            "supplier":   g["supplier"],
            "unit":       g["unit"],
            "total_qty":  g["total_qty"],
            "po_sources": ", ".join(sorted(g["po_list"])),
        })

    # Meta
    po_numbers = sorted({s.get("po_number", "") for s in selected.values() if s.get("po_number")})
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    meta = {
        "po_count":    len(selected),
        "po_numbers":  ", ".join(po_numbers),
        "date":        datetime.now().strftime("%d/%m/%Y"),
        "prepared_by": "AI Agent",
    }

    # Export Excel
    output_path = os.path.join(OUTPUT_DIR, f"recap_aggregate_{timestamp}.xlsx")
    RecapAggregateExporter.export(
        aggregated_items=aggregated,
        output_path=output_path,
        meta=meta,
    )

    result = {
        "status":      "success",
        "timestamp":   timestamp,
        "meta":        meta,
        "total_items": len(aggregated),
        "total_qty":   sum(i["total_qty"] for i in aggregated),
        "items":       aggregated,
        "excel_path":  output_path,
    }

    # Lưu lịch sử
    _save_history({
        "timestamp":   timestamp,
        "saved_at":    datetime.now().strftime("%d/%m/%Y %H:%M"),
        "po_count":    meta["po_count"],
        "po_numbers":  meta["po_numbers"],
        "total_items": len(aggregated),
        "total_qty":   sum(i["total_qty"] for i in aggregated),
        "session_ids": body.session_ids,
    })

    return result


@router.post("/send-email")
def send_email(body: SendEmailRequest):
    """Gửi file Recap Excel qua Gmail đến địa chỉ email chỉ định."""
    excel_path = os.path.join(OUTPUT_DIR, f"recap_aggregate_{body.timestamp}.xlsx")
    if not os.path.exists(excel_path):
        raise HTTPException(404, "File Excel không tồn tại — vui lòng tổng hợp lại trước")

    subject = f"[MCNA] Recap Trim List — {body.po_numbers or body.timestamp}"
    html_body = f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
  <p>Kính gửi,</p>
  <p>Vui lòng xem file <strong>Recap Trim List</strong> đính kèm.</p>
  <table style="border-collapse: collapse; margin: 16px 0;">
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">PO:</td>
        <td style="padding: 4px 0;"><strong>{body.po_numbers or "—"}</strong></td></tr>
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Số loại trim:</td>
        <td style="padding: 4px 0;"><strong>{body.total_items}</strong></td></tr>
    <tr><td style="padding: 4px 12px 4px 0; color: #666;">Tổng qty:</td>
        <td style="padding: 4px 0;"><strong>{body.total_qty:,}</strong></td></tr>
  </table>
  <p style="color: #999; font-size: 12px;">Email được gửi tự động từ hệ thống AI Agent — MCNA Garment</p>
</div>
"""
    try:
        send_trimlist_email(
            to_email=body.to_email,
            subject=subject,
            body=html_body,
            attachment_path=excel_path,
        )
    except Exception as e:
        raise HTTPException(500, f"Gửi email thất bại: {e}")

    return {"status": "success", "message": f"Đã gửi email đến {body.to_email}"}


@router.get("/download/{timestamp}")
def download_recap(timestamp: str):
    path = os.path.join(OUTPUT_DIR, f"recap_aggregate_{timestamp}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"RecapTrim_{timestamp}.xlsx",
    )
