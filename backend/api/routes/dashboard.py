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


@router.get("/tasks")
def get_task_dashboard():
    """Combined Task A (PO↔GO) + Task B (Trimlist) dashboard: KPIs, trends,
    and the queue of runs that still need a human."""
    from backend.services.run_history import read_runs

    runs_a = read_runs("A", limit=100)
    runs_b = read_runs("B", limit=100)

    def _avg(vals):
        vals = [v for v in vals if isinstance(v, (int, float))]
        return round(sum(vals) / len(vals)) if vals else None

    a_latest = runs_a[0] if runs_a else None
    b_latest = runs_b[0] if runs_b else None

    # Trend: last 10 runs (oldest → newest) for the sparkline charts
    trend_a = [{"at": r.get("at", "")[5:16], "value": r.get("match_rate")}
               for r in reversed(runs_a[:10]) if r.get("match_rate") is not None]
    trend_b = [{"at": r.get("at", "")[5:16], "value": r.get("complete_rate")}
               for r in reversed(runs_b[:10]) if r.get("complete_rate") is not None]

    # Action queue — runs that still need attention, most recent first
    queue = []
    for r in runs_a[:20]:
        need = (r.get("errors") or 0) > 0 or (r.get("mismatched") or 0) > 0 or (r.get("qty_diff") or 0) != 0
        if need:
            queue.append({
                "task": "A", "at": r.get("at", ""), "ref": r.get("po_number") or r.get("token", ""),
                "headline": f"{r.get('mismatched', 0)} dòng lệch · chênh {r.get('qty_diff', 0):+} pcs",
                "errors": r.get("errors", 0), "link": "/task-a",
            })
    for r in runs_b[:20]:
        miss = r.get("missing") or {}
        need = (r.get("errors") or 0) > 0 or (r.get("incomplete_items") or 0) > 0 or (r.get("recovered") or 0) > 0
        if need:
            top = sorted(miss.items(), key=lambda kv: kv[1] or 0, reverse=True)[:2]
            top_txt = ", ".join(f"{k.replace('missing_', '')}: {v}" for k, v in top if v)
            queue.append({
                "task": "B", "at": r.get("at", ""), "ref": r.get("style_code") or r.get("excel_token", ""),
                "headline": f"{r.get('incomplete_items', 0)} dòng thiếu" + (f" ({top_txt})" if top_txt else ""),
                "errors": r.get("errors", 0), "link": "/task-b",
            })
    queue.sort(key=lambda x: x.get("at", ""), reverse=True)

    return {
        "kpi": {
            "runs_a":        len(runs_a),
            "runs_b":        len(runs_b),
            "avg_match":     _avg([r.get("match_rate") for r in runs_a]),
            "avg_complete":  _avg([r.get("complete_rate") for r in runs_b]),
            "open_issues":   len(queue),
        },
        "task_a": {
            "latest": a_latest,
            "trend":  trend_a,
        },
        "task_b": {
            "latest": b_latest,
            "trend":  trend_b,
            "missing": (b_latest or {}).get("missing") or {},
        },
        "queue":  queue[:12],
        "recent": (runs_a[:5] + runs_b[:5]),
    }


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
