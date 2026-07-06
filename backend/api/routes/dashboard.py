"""
GET /api/dashboard/stats — Tổng hợp số liệu cho Dashboard.
Lấy từ: scan log (file system) + Supabase PO history + trimlist files.
"""
import os
import glob
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter

from backend.services.scan_service import get_processed_log, get_all_po_files

logger = logging.getLogger(__name__)
router = APIRouter()

OUTPUT_DIR = "sample_data"


@router.get("/stats")
def get_dashboard_stats():
    log       = get_processed_log()
    all_files = get_all_po_files()

    # ── Tổng quan ──────────────────────────────────────────────────────────────
    total_files    = len(all_files)
    processed      = [v for v in log.values() if v.get("status") in ("success", "partial")]
    failed         = [v for v in log.values() if v.get("status") == "error"]
    success_count  = len([v for v in log.values() if v.get("status") == "success"])
    partial_count  = len([v for v in log.values() if v.get("status") == "partial"])
    total_trim     = sum(v.get("trim_count", 0) or 0 for v in log.values())
    total_qty      = sum(v.get("total_qty", 0) or 0 for v in log.values())

    # ── Trimlist files ──────────────────────────────────────────────────────────
    trim_files = sorted(glob.glob(f"{OUTPUT_DIR}/trimlist/trimlist_*.xlsx"), reverse=True)

    # ── Hoạt động 7 ngày gần nhất (từ log) ────────────────────────────────────
    today     = datetime.now().date()
    day_map   = defaultdict(int)
    for entry in log.values():
        try:
            dt  = datetime.strptime(entry["processed_at"], "%Y-%m-%d %H:%M:%S")
            key = dt.strftime("%d/%m")
            day_map[key] += 1
        except Exception:
            pass

    activity = []
    for i in range(6, -1, -1):
        d   = today - timedelta(days=i)
        key = d.strftime("%d/%m")
        activity.append({"date": key, "count": day_map.get(key, 0)})

    # ── 5 file gần nhất ────────────────────────────────────────────────────────
    recent = sorted(log.items(), key=lambda x: x[1].get("processed_at", ""), reverse=True)[:5]
    recent_list = [
        {
            "filename":     fname,
            "processed_at": v.get("processed_at", ""),
            "status":       v.get("status", ""),
            "po_number":    v.get("po_number", ""),
            "style_code":   v.get("style_code", ""),
            "total_qty":    v.get("total_qty", 0),
            "trim_count":   v.get("trim_count", 0),
            "timestamp":    v.get("timestamp", ""),
        }
        for fname, v in recent
    ]

    return {
        "overview": {
            "total_files":    total_files,
            "processed":      len(processed) + len(failed),
            "success":        success_count,
            "partial":        partial_count,
            "failed":         len(failed),
            "pending":        max(0, total_files - len(log)),
            "total_trim_items": total_trim,
            "total_qty":      total_qty,
            "trimlist_files": len(trim_files),
        },
        "activity_7days": activity,
        "recent_files":   recent_list,
    }
