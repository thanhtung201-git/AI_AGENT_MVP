"""
compare.py — API endpoints so sánh GO vs PO.

POST /api/compare/go-vs-po  — so sánh và trả JSON + (tùy chọn) export Excel
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.extractors.go_extractor import GOExtractor
from backend.extractors.hzsh_extractor import HZSHExtractor
from backend.services.format_understander import FormatUnderstander
from backend.services.go_compare_service import GOCompareService
from backend.exporters.compare_exporter import CompareExporter
from tools.excel_reader import read_excel_structured

router = APIRouter(prefix="/api/compare", tags=["compare"])
logger = logging.getLogger(__name__)

OUTPUT_DIR = os.path.join("sample_data", "compare")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class CompareRequest(BaseModel):
    po_file:      str                 # đường dẫn PO Excel (bắt buộc)
    hzsh_file:    Optional[str] = None  # HZSH để lấy size/lot breakdown
    go_info_file: Optional[str] = None  # GO Information file (tùy chọn)
    export_excel: bool = True           # có tạo file Excel không


@router.post("/go-vs-po")
def compare_go_vs_po(req: CompareRequest):
    """
    So sánh GO (HZSH + GO Information) với PO.

    Ít nhất phải có: po_file + (hzsh_file hoặc go_info_file).
    """
    # Validate
    if not os.path.exists(req.po_file):
        raise HTTPException(400, f"Không tìm thấy PO file: {req.po_file}")
    if not req.hzsh_file and not req.go_info_file:
        raise HTTPException(400, "Cần ít nhất một trong: hzsh_file hoặc go_info_file")

    # Step 1: Extract PO
    logger.info(f"Compare: đọc PO {req.po_file}")
    structured = read_excel_structured(req.po_file)
    if not structured["success"]:
        raise HTTPException(422, f"Không đọc được PO: {structured['error']}")

    fu_result = FormatUnderstander().extract(structured)
    if not fu_result["success"]:
        raise HTTPException(422, f"Không extract được PO: {fu_result['error']}")
    po_data = fu_result["data"]

    # Step 2: Extract HZSH (nếu có)
    hzsh_data = {}
    if req.hzsh_file:
        if not os.path.exists(req.hzsh_file):
            raise HTTPException(400, f"Không tìm thấy HZSH: {req.hzsh_file}")
        logger.info(f"Compare: đọc HZSH {req.hzsh_file}")
        hzsh_result = HZSHExtractor().extract(req.hzsh_file)
        if hzsh_result["success"]:
            hzsh_data = hzsh_result["data"]
        else:
            logger.warning(f"HZSH extract fail: {hzsh_result['error']}")

    # Step 3: Extract GO Information (nếu có)
    go_data = {}
    if req.go_info_file:
        if not os.path.exists(req.go_info_file):
            raise HTTPException(400, f"Không tìm thấy GO Info: {req.go_info_file}")
        logger.info(f"Compare: đọc GO Info {req.go_info_file}")
        go_result = GOExtractor().extract(req.go_info_file)
        if go_result["success"]:
            go_data = go_result["data"]
        else:
            logger.warning(f"GO extract fail: {go_result['error']}")

    # Nếu không có go_data nhưng có hzsh_data, dùng HZSH làm GO proxy
    if not go_data and hzsh_data:
        go_data = {
            "style_no":  hzsh_data.get("style_no", ""),
            "season":    hzsh_data.get("season", ""),
            "colors":    hzsh_data.get("colors", []),
            "total_qty": sum(c.get("total_qty", 0) for c in hzsh_data.get("colors", [])),
        }

    # Step 4: Compare
    compare_result = GOCompareService().compare(go_data, po_data, hzsh_data)

    # Step 5: Export Excel (tùy chọn)
    excel_path = None
    if req.export_excel:
        export_result = CompareExporter.export(compare_result, output_dir=OUTPUT_DIR)
        if export_result["success"]:
            excel_path = export_result["output_path"]
        else:
            logger.warning(f"Export Excel fail: {export_result['error']}")

    return {
        "status":         "success",
        "compare_result": compare_result,
        "excel_path":     excel_path,
    }


@router.get("/download")
def download_compare_report(filename: str):
    """Download file báo cáo so sánh."""
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
