"""
POST /api/trimlist/process  — Upload techpack + truyền PO data → tạo trimlist.
GET  /api/trimlist/download/{timestamp} — Download file Excel trimlist.
"""
import os
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from tools.reader import read_file
from backend.extractors.trimlist_extractor import TrimlistExtractor
from backend.exporters.trimlist_exporter import TrimlistExporter

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "sample_data/uploads/techpack"
OUTPUT_DIR = "sample_data/trimlist"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@router.post("/process")
async def process_trimlist(
    file: UploadFile = File(...),
    po_number:  str = Form(""),
    style_code: str = Form(""),
    style_name: str = Form(""),
    buyer:      str = Form(""),
    factory:    str = Form(""),
    order_qty:  int = Form(0),
    season:     str = Form(""),
):
    """
    Upload file Techpack → trích xuất trim list → trả về kết quả + Excel.
    """
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in (".pdf", ".xlsx", ".xls", ".docx"):
        raise HTTPException(400, "Chỉ hỗ trợ PDF, Excel, Word")

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path = os.path.join(UPLOAD_DIR, f"techpack_{timestamp}{ext}")

    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    # Đọc file techpack
    read_result = read_file(saved_path)
    if not read_result.get("success"):
        raise HTTPException(422, f"Không đọc được file: {read_result.get('error')}")

    raw_text = read_result["text"]
    logger.info(f"Techpack đọc OK: {len(raw_text)} ký tự")

    # Trích xuất trim
    try:
        extractor  = TrimlistExtractor()
        trim_items = extractor.extract(raw_text, order_qty=order_qty)
    except RuntimeError as e:
        if "RATE LIMIT" in str(e):
            raise HTTPException(429, str(e))
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error(f"TrimlistExtractor lỗi: {e}")
        raise HTTPException(500, f"Trích xuất trim thất bại: {str(e)}")

    if not trim_items:
        raise HTTPException(422, "Không tìm thấy trim items trong file techpack")

    # Export Excel
    meta = {
        "po_number":   po_number,
        "style_code":  style_code,
        "style_name":  style_name,
        "buyer":       buyer,
        "order_qty":   f"{order_qty:,} pcs" if order_qty else "",
        "factory":     factory,
        "season":      season,
        "date":        datetime.now().strftime("%d/%m/%Y"),
        "prepared_by": "AI Agent",
    }
    output_path = os.path.join(OUTPUT_DIR, f"trimlist_{timestamp}.xlsx")
    TrimlistExporter.export(trim_items=trim_items, output_path=output_path, meta=meta)

    return {
        "status":      "success",
        "timestamp":   timestamp,
        "item_count":  len(trim_items),
        "trim_items":  trim_items,
        "excel_path":  output_path,
    }


@router.get("/download/{timestamp}")
def download_trimlist_excel(timestamp: str):
    """Download file Excel trimlist đã tạo."""
    path = os.path.join(OUTPUT_DIR, f"trimlist_{timestamp}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"Trimlist_{timestamp}.xlsx",
    )
