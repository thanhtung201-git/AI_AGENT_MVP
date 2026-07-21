"""
run_history.py — Lightweight run log so the dashboard can show trends.

Task A (PO ↔ GO Compare) and Task B (Trimlist) return their result and forget it.
The dashboard needs "how did we do over time", so each run appends one small summary
record here. Only summary metrics are stored (no item payloads) — the file stays tiny
and the dashboard reads it instantly, with no database dependency.
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_PATH = os.path.join("sample_data", ".run_history.json")
_MAX  = 300   # keep the most recent N runs


def _load() -> List[Dict[str, Any]]:
    if not os.path.exists(_PATH):
        return []
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(runs: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(_PATH)), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(runs[-_MAX:], f, ensure_ascii=False, indent=1)


def log_run(record: Dict[str, Any]) -> None:
    """Append one run summary. Never raises — logging must not break a run."""
    try:
        record = dict(record)
        record.setdefault("at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        runs = _load()
        runs.append(record)
        _save(runs)
    except Exception as e:
        logger.warning(f"run_history.log_run failed (non-fatal): {e}")


def read_runs(task: str = "", limit: int = 300) -> List[Dict[str, Any]]:
    """Most recent first. `task` = "A" | "B" | "" (all)."""
    runs = _load()
    if task:
        runs = [r for r in runs if r.get("task") == task]
    return list(reversed(runs))[:limit]


# ── Builders: turn a pipeline result into a compact summary record ───────────

def summarize_task_a(result: Dict[str, Any]) -> Dict[str, Any]:
    cmp_    = result.get("compare") or {}
    summary = cmp_.get("summary") or {}
    rows    = cmp_.get("rows") or []
    matched = sum(1 for r in rows if (r.get("status") or "").upper() == "MATCH")
    total   = len(rows)
    po      = result.get("po") or {}
    return {
        "task":        "A",
        "status":      summary.get("status") or "",
        "match_rate":  round(matched * 100 / total) if total else None,
        "rows":        total,
        "mismatched":  total - matched,
        "errors":      summary.get("errors", 0),
        "warnings":    summary.get("warnings", 0),
        "po_total":    summary.get("po_total", 0),
        "go_total":    summary.get("go_total", 0),
        "qty_diff":    summary.get("qty_diff", 0),
        "po_number":   (po.get("po_number") or {}).get("value") if isinstance(po.get("po_number"), dict) else po.get("po_number") or "",
        "go_source":   result.get("go_source") or "",
        "token":       result.get("token") or "",
    }


def summarize_task_b(result: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    comp   = result.get("completion") or {}
    alerts = result.get("alert_summary") or {}
    branch = result.get("branch") or {}
    recon  = result.get("reconciliation") or {}
    total  = comp.get("total_items") or result.get("item_count") or 0
    done   = comp.get("complete_items") or 0
    return {
        "task":            "B",
        "style_code":      meta.get("style_code") or "",
        "branch":          branch.get("used") or "",
        "branch_conf":     branch.get("confidence") or "",
        "item_count":      result.get("item_count", 0),
        "complete_items":  done,
        "incomplete_items": comp.get("incomplete_items", 0),
        "complete_rate":   round(done * 100 / total) if total else None,
        "errors":          alerts.get("errors", 0),
        "warnings":        alerts.get("warnings", 0),
        "missing":         comp.get("pending_summary") or {},
        "recovered":       recon.get("recovered", 0),
        "excel_token":     result.get("excel_token") or "",
    }
