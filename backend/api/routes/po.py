"""
POST /api/po/process  — Upload file PO → trả về kết quả trích xuất + đường dẫn Excel.
GET  /api/po/{po_id}  — Lấy chi tiết 1 PO từ Supabase.
"""
import os
import io
import glob
import shutil
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from backend.agents.po_agent import POAgent
from backend.exporters.json_exporter import JsonExporter
from backend.exporters.excel_exporter import ExcelExporter
from backend.normalization.mapper import DataMapper
from backend.schemas.canonical import CanonicalSchema
from backend.database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "sample_data/uploads"
OUTPUT_DIR = "sample_data"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@router.post("/process")
async def process_po(file: UploadFile = File(...)):
    """
    Upload file PO (PDF hoặc Excel) → chạy AI Agent → trả kết quả JSON.
    """
    # Lưu file upload tạm
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in (".pdf", ".xlsx", ".xls"):
        raise HTTPException(400, "Chỉ hỗ trợ file PDF hoặc Excel (.pdf, .xlsx, .xls)")

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path = os.path.join(UPLOAD_DIR, f"po_{timestamp}{ext}")

    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    logger.info(f"Đã lưu file upload: {saved_path}")

    # Chạy PO Agent
    try:
        agent  = POAgent()
        result = agent.process_request(
            user_request="Extract PO từ file và lưu vào database",
            file_path=saved_path,
        )
    except Exception as e:
        logger.error(f"PO Agent lỗi: {e}")
        raise HTTPException(500, f"AI Agent lỗi: {str(e)}")

    if result["status"] != "success":
        raise HTTPException(422, f"Trích xuất thất bại: {result.get('reason', 'Unknown error')}")

    results = result.get("results", {})
    header  = results.get("header_extractor", {}).get("header", {})
    items   = results.get("item_extractor",  {}).get("items",  [])

    combined = {
        **header,
        "items": items,
        "total_quantity_all": sum(i.get("total_quantity") or 0 for i in items),
        "total_amount":       sum(i.get("total_price")    or 0.0 for i in items),
    }
    normalized = DataMapper.map_po_data(combined)
    po_model   = CanonicalSchema.validate_and_load(normalized)

    # Export files
    json_path  = os.path.join(OUTPUT_DIR, f"output_po_{timestamp}.json")
    excel_path = os.path.join(OUTPUT_DIR, f"output_po_{timestamp}.xlsx")
    JsonExporter.export(po_model, json_path)
    ExcelExporter.export(po_model, excel_path)

    # Lưu Supabase
    po_id = None
    try:
        db    = SupabaseClient()
        po_id = db.insert_po(header=header, items=items)
    except Exception as e:
        logger.warning(f"Supabase insert bỏ qua: {e}")

    style_code = po_model.items[0].style_code if po_model.items else None
    total_qty  = po_model.total_quantity_all or sum(i.total_quantity or 0 for i in po_model.items)
    style_name = getattr(po_model, "style_name", "") or ""
    factory    = getattr(po_model, "factory", "") or ""

    return {
        "status":       "success",
        "po_id":        po_id,
        "timestamp":    timestamp,
        "po_number":    po_model.po_number,
        "style_code":   style_code,
        "style_name":   style_name,
        "buyer":        po_model.buyer,
        "factory":      factory,
        "total_qty":    total_qty,
        "total_amount": po_model.total_amount,
        "item_count":   len(po_model.items),
        "items":        [i.model_dump() for i in po_model.items],
        "excel_path":   excel_path,
        "json_path":    json_path,
    }


@router.get("/download/{timestamp}")
def download_po_excel(timestamp: str):
    """Download file Excel PO đã tạo."""
    path = os.path.join(OUTPUT_DIR, f"output_po_{timestamp}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=f"PO_{timestamp}.xlsx")
