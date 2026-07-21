"""
upload_history.py — API lưu/đọc lịch sử trang Upload File.

GET  /api/upload-history        — lấy danh sách (mới nhất trước)
POST /api/upload-history        — lưu một entry sau khi xử lý xong
"""

import logging
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from backend.database.supabase_client import SupabaseClient

router = APIRouter(prefix="/api/upload-history", tags=["upload-history"])
logger = logging.getLogger(__name__)
db = SupabaseClient()


class HistoryEntry(BaseModel):
    filename:     str
    status:       str                   # success | partial | error
    po_number:    Optional[str] = None
    style_code:   Optional[str] = None
    total_qty:    Optional[int] = None
    trim_count:   Optional[int] = None
    timestamp:    Optional[str] = None  # để download file sau
    warning:      Optional[str] = None
    error:        Optional[str] = None
    has_techpack: bool = False


@router.get("")
def get_history(limit: int = 50):
    rows = db.upload_history_get(limit=limit)
    return {"success": True, "data": rows, "total": len(rows)}


@router.post("")
def save_history(entry: HistoryEntry):
    ok = db.upload_history_insert(entry.model_dump())
    return {"success": ok}
