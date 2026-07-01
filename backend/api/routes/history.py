"""
GET /api/history/po       — Lịch sử PO từ Supabase.
GET /api/history/trimlist — Danh sách file trimlist đã tạo (từ filesystem).
"""
import os
import glob
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException

from backend.database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/po")
def get_po_history(limit: int = 20):
    """Lấy danh sách PO đã xử lý từ Supabase."""
    try:
        db   = SupabaseClient()
        rows = db.get_po_list(limit=limit)
        return {"status": "success", "count": len(rows), "data": rows}
    except Exception as e:
        logger.error(f"Supabase lỗi: {e}")
        raise HTTPException(500, f"Không lấy được lịch sử: {str(e)}")


@router.get("/trimlist")
def get_trimlist_history():
    """Danh sách file trimlist Excel đã tạo (từ filesystem)."""
    output_dir = "sample_data/trimlist"
    files = sorted(glob.glob(f"{output_dir}/trimlist_*.xlsx"), reverse=True)
    result = []
    for f in files:
        name = os.path.basename(f)
        ts   = name.replace("trimlist_", "").replace(".xlsx", "")
        try:
            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
            created_at = dt.strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            created_at = ts
        result.append({
            "filename":   name,
            "timestamp":  ts,
            "created_at": created_at,
            "size_kb":    round(os.path.getsize(f) / 1024, 1),
        })
    return {"status": "success", "count": len(result), "data": result}
