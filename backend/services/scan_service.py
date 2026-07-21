"""
Scan service — quét folder PO, theo dõi file đã xử lý qua Supabase scan_log.
Fallback về JSON file nếu Supabase không kết nối được.
"""
import os
import json
import glob
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Repo-relative so it works on any machine / Linux host (was a hardcoded C:\ path).
_BASE         = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "sample_data",
)
SCAN_FOLDER   = os.path.join(_BASE, "data_test")       # PO folder (giữ nguyên)
HAZZYS_FOLDER = os.path.join(_BASE, "Hazzys")          # folder đối tác Hazzys
LOG_FILE      = "sample_data/.processed_log.json"      # fallback JSON
ALLOWED_EXT   = {".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".doc",
                 ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp",
                 ".eml", ".msg"}

# Nhận biết loại file trong folder Hazzys theo tên file
# Template (Batch GO Upload.xlsx) không được scan — chỉ dùng làm base khi generate
_HAZZYS_SKIP_PATTERNS = ["batch go upload"]

def detect_hazzys_file_type(filename: str) -> str:
    """
    Nhận biết loại file đối tác theo tên file.
    Returns: 'hzsh' | 'go_info' | 'master_trim' | 'template' | 'unknown'
    """
    name_lower = filename.lower()
    if name_lower.startswith("hzsh"):
        return "hzsh"
    if "go information" in name_lower or name_lower.startswith("go info"):
        return "go_info"
    if "trim master" in name_lower or "packing trim" in name_lower:
        return "master_trim"
    if "batch go upload" in name_lower:
        return "template"   # bỏ qua — không scan
    return "unknown"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_db():
    """Trả về SupabaseClient (lazy import để tránh circular)."""
    from backend.database.supabase_client import SupabaseClient
    return SupabaseClient()


def _load_json_log() -> Dict[str, Any]:
    if not os.path.exists(LOG_FILE):
        return {}
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_log(log: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(LOG_FILE)), exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8", errors="replace") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def get_all_po_files() -> List[str]:
    if not os.path.exists(SCAN_FOLDER):
        return []
    files = []
    for ext in ALLOWED_EXT:
        files += glob.glob(os.path.join(SCAN_FOLDER, f"*{ext}"))
        files += glob.glob(os.path.join(SCAN_FOLDER, f"*{ext.upper()}"))
    return sorted(set(files))


def get_hazzys_files(file_type: str = None) -> List[Dict[str, str]]:
    """
    Lấy danh sách file trong folder Hazzys/, có thể lọc theo loại.

    Args:
        file_type: 'hzsh' | 'go_info' | 'master_trim' | None (lấy tất cả trừ template)

    Returns:
        List[{"path": str, "filename": str, "file_type": str}]
    """
    if not os.path.exists(HAZZYS_FOLDER):
        logger.warning(f"Folder Hazzys không tồn tại: {HAZZYS_FOLDER}")
        return []

    result = []
    for ext in {".xlsx", ".xls", ".xlsm", ".pdf"}:
        for path in glob.glob(os.path.join(HAZZYS_FOLDER, f"*{ext}")):
            filename = os.path.basename(path)
            ftype = detect_hazzys_file_type(filename)
            if ftype == "template":
                continue   # bỏ qua template
            if file_type and ftype != file_type:
                continue
            result.append({"path": path, "filename": filename, "file_type": ftype})

    return sorted(result, key=lambda x: x["filename"])


def get_processed_log() -> Dict[str, Any]:
    """JSON là nguồn chính — luôn đọc từ file local."""
    return _load_json_log()


def get_new_files() -> List[str]:
    log   = get_processed_log()
    all_f = get_all_po_files()
    known = set(log.keys())
    return [f for f in all_f if os.path.basename(f) not in known]


def mark_processed(file_path: str, result: Dict[str, Any]) -> None:
    filename = os.path.basename(file_path)
    entry = {
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_path":    file_path,
        "status":       result.get("status", "unknown"),
        "timestamp":    result.get("timestamp", ""),
        "po_number":    result.get("po", {}).get("po_number", ""),
        "style_code":   result.get("po", {}).get("style_code", ""),
        "total_qty":    result.get("po", {}).get("total_qty", 0),
        "trim_count":   result.get("trimlist", {}).get("item_count", 0) if result.get("trimlist") else 0,
        "po_id":        result.get("po", {}).get("po_id"),
        "session_id":   result.get("trimlist", {}).get("session_id") if result.get("trimlist") else None,
        "warning":      result.get("warning", ""),
    }
    # Luôn ghi JSON trước
    log = _load_json_log()
    log[filename] = entry
    _save_json_log(log)
    # Sync Supabase
    try:
        db = _get_db()
        if not db.mock_mode:
            db.scan_log_upsert(filename, entry)
    except Exception as e:
        logger.warning(f"Supabase scan_log sync that bai: {e}")


def mark_failed(file_path: str, error: str) -> None:
    filename = os.path.basename(file_path)
    entry = {
        "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file_path":    file_path,
        "status":       "error",
        "error":        error,
    }
    log = _load_json_log()
    log[filename] = entry
    _save_json_log(log)
    try:
        db = _get_db()
        if not db.mock_mode:
            db.scan_log_upsert(filename, entry)
    except Exception:
        pass


def reset_file(filename: str) -> bool:
    """Xóa file khỏi log để xử lý lại."""
    log = _load_json_log()
    if filename not in log:
        return False
    del log[filename]
    _save_json_log(log)
    try:
        db = _get_db()
        if not db.mock_mode:
            db.scan_log_delete(filename)
    except Exception:
        pass
    return True
