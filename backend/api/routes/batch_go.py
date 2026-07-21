"""
batch_go.py — API endpoints cho tính năng Batch GO Upload.

POST /api/batch-go/generate  — tạo file Batch GO từ HZSH + PO
GET  /api/batch-go/hazzys-files — liệt kê file trong folder Hazzys/
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from backend.extractors.hzsh_extractor import HZSHExtractor
from backend.services.format_understander import FormatUnderstander
from backend.exporters.batch_go_exporter import BatchGOExporter
from backend.services.scan_service import get_hazzys_files
from tools.excel_reader import read_excel_structured

router = APIRouter(prefix="/api/batch-go", tags=["batch-go"])
logger = logging.getLogger(__name__)


class GenerateRequest(BaseModel):
    hzsh_file: str          # đường dẫn file HZSH (từ folder Hazzys/)
    po_file: Optional[str] = None   # đường dẫn PO file (tùy chọn)


@router.get("/hazzys-files")
def list_hazzys_files():
    """Liệt kê file trong folder Hazzys/ theo loại."""
    files = get_hazzys_files()
    grouped = {"hzsh": [], "go_info": [], "master_trim": [], "unknown": []}
    for f in files:
        ftype = f["file_type"]
        grouped.setdefault(ftype, []).append({
            "filename": f["filename"],
            "path":     f["path"],
        })
    return {"success": True, "files": grouped, "total": len(files)}


@router.post("/generate")
def generate_batch_go(req: GenerateRequest):
    """
    Tạo file Batch GO Upload từ file HZSH (+ PO nếu có).

    Steps:
      1. HZSHExtractor đọc file HZSH → color/lot structure
      2. FormatUnderstander đọc PO (nếu có) → po_data
      3. BatchGOExporter sinh file Excel eSCM
    """
    # Validate files tồn tại
    if not os.path.exists(req.hzsh_file):
        raise HTTPException(status_code=400, detail=f"Không tìm thấy file HZSH: {req.hzsh_file}")

    # Step 1: Extract HZSH
    logger.info(f"Batch GO generate: HZSH={req.hzsh_file}")
    hzsh_result = HZSHExtractor().extract(req.hzsh_file)
    if not hzsh_result["success"]:
        raise HTTPException(status_code=422, detail=f"Lỗi đọc HZSH: {hzsh_result['error']}")

    hzsh_data = hzsh_result["data"]

    # Step 2: Extract PO (nếu có)
    po_data = {}
    if req.po_file and os.path.exists(req.po_file):
        logger.info(f"Batch GO generate: PO={req.po_file}")
        structured = read_excel_structured(req.po_file)
        if structured["success"]:
            fu_result = FormatUnderstander().extract(structured)
            if fu_result["success"]:
                po_data = fu_result["data"]
            else:
                logger.warning(f"FormatUnderstander fail: {fu_result['error']}")
        else:
            logger.warning(f"Không đọc được PO file: {structured['error']}")

    # Step 3: Generate Batch GO
    result = BatchGOExporter().export(hzsh_data, po_data)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Lỗi tạo Batch GO: {result['error']}")

    output_path = result["output_path"]
    filename = os.path.basename(output_path)

    return FileResponse(
        path=output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
