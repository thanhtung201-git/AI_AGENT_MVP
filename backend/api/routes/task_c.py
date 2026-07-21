"""
POST /api/task-c/run  — Upload Trimlist → Verify từng dòng bằng LLM
"""
import os
import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "sample_data/uploads/task_c"
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def _save_upload(file: UploadFile, prefix: str) -> str:
    from datetime import datetime
    ext  = os.path.splitext(file.filename)[-1].lower()
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(UPLOAD_DIR, f"{prefix}_{ts}{ext}")
    content = await file.read()
    with open(path, "wb") as f:
        f.write(content)
    return path


@router.post("/run")
async def run_task_c(
    trimlist_file:    UploadFile = File(...),
    techpack_file:    Optional[UploadFile] = File(None),
    master_trim_file: Optional[UploadFile] = File(None),
    garment_type:     str = Form("Men Woven"),
):
    """Upload Trimlist Excel → AI verify từng dòng → báo cáo."""
    ext = os.path.splitext(trimlist_file.filename)[-1].lower()
    if ext not in (".xlsx", ".xls", ".pdf"):
        raise HTTPException(400, "Trimlist: chỉ hỗ trợ Excel hoặc PDF")

    trimlist_path = await _save_upload(trimlist_file, "trimlist")

    techpack_path: Optional[str] = None
    if techpack_file and techpack_file.filename:
        techpack_path = await _save_upload(techpack_file, "techpack")

    master_path: Optional[str] = None
    if master_trim_file and master_trim_file.filename:
        master_path = await _save_upload(master_trim_file, "master")

    from backend.services.task_c_service import TaskCService
    service = TaskCService()
    result  = service.run(
        trimlist_path=trimlist_path,
        techpack_path=techpack_path,
        master_trim_path=master_path,
        garment_type=garment_type,
    )

    if not result.get("success"):
        raise HTTPException(500, result.get("error") or "Task C thất bại")

    return result
