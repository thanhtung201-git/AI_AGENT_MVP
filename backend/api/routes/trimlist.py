"""
POST /api/trimlist/process       — Upload techpack + truyền PO data → tạo trimlist.
POST /api/trimlist/hazzys        — Tạo trimlist Hazzys format từ Master Trim + HZSH.
GET  /api/trimlist/download/{ts} — Download file Excel trimlist.
"""
import os
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from tools.reader import read_file
from backend.extractors.trimlist_extractor import TrimlistExtractor
from backend.extractors.master_trim_reader import MasterTrimReader
from backend.extractors.hzsh_extractor import HZSHExtractor
from backend.exporters.trimlist_exporter import TrimlistExporter
from backend.services.scan_service import HAZZYS_FOLDER

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


class HazzysTrimlistRequest(BaseModel):
    master_trim_file: str        # đường dẫn file Master Trim trong Hazzys/
    garment_type: str            # vd "Men Woven", "Ladies Knit"
    hzsh_file: Optional[str] = None  # để lấy color list + total qty
    po_number:  str = ""
    style_code: str = ""
    style_name: str = ""
    buyer:      str = "HAZZYS"
    season:     str = ""


@router.post("/hazzys")
def generate_hazzys_trimlist(req: HazzysTrimlistRequest):
    """
    Tạo Trimlist Hazzys format từ Master Trim Excel + (tùy chọn) HZSH.

    Flow:
      1. MasterTrimReader đọc sheet đúng garment type
      2. HZSHExtractor đọc HZSH lấy color list (nếu có)
      3. TrimlistExporter.export_hazzys() tạo file grouped + color columns
    """
    # Validate
    if not os.path.exists(req.master_trim_file):
        raise HTTPException(400, f"Không tìm thấy Master Trim: {req.master_trim_file}")

    # Step 1: Đọc Master Trim
    reader     = MasterTrimReader(req.master_trim_file)
    read_result = reader.read(req.garment_type)
    if not read_result["success"]:
        raise HTTPException(422, f"Lỗi đọc Master Trim: {read_result['error']}")

    trim_items = read_result["items"]
    if not trim_items:
        raise HTTPException(422, f"Không có trim items trong sheet '{read_result['sheet']}'")

    # Step 2: Lấy colors từ HZSH (nếu có)
    colors = []
    if req.hzsh_file and os.path.exists(req.hzsh_file):
        hzsh_result = HZSHExtractor().extract(req.hzsh_file)
        if hzsh_result["success"]:
            colors = hzsh_result["data"].get("colors", [])
        else:
            logger.warning(f"HZSH extract fail: {hzsh_result['error']}")

    # Step 3: Export
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"trimlist_hazzys_{timestamp}.xlsx")
    meta = {
        "po_number":   req.po_number,
        "style_code":  req.style_code,
        "style_name":  req.style_name,
        "buyer":       req.buyer,
        "season":      req.season,
        "date":        datetime.now().strftime("%d/%m/%Y"),
        "prepared_by": "AI Agent",
    }

    TrimlistExporter.export_hazzys(
        trim_items=trim_items,
        output_path=output_path,
        meta=meta,
        colors=colors,
    )

    filename = os.path.basename(output_path)

    # Trả JSON nếu client muốn metadata, nhưng cũng cung cấp download_url
    return {
        "status":       "success",
        "timestamp":    timestamp,
        "item_count":   len(trim_items),
        "sheet_used":   read_result["sheet"],
        "colors":       [c.get("color_code") for c in colors],
        "excel_path":   output_path,
        "download_url": f"/api/trimlist/download-file/{filename}",
    }


@router.get("/download/{timestamp}")
def download_trimlist_excel(timestamp: str):
    """Download file Excel trimlist (flat format) theo timestamp."""
    path = os.path.join(OUTPUT_DIR, f"trimlist_{timestamp}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"Trimlist_{timestamp}.xlsx",
    )


@router.get("/download-file/{filename}")
def download_trimlist_by_filename(filename: str):
    """Download file Excel trimlist theo tên file (dùng cho Hazzys format)."""
    # Chỉ cho phép tải file trong OUTPUT_DIR
    safe_name = os.path.basename(filename)  # ngăn path traversal
    path = os.path.join(OUTPUT_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(404, f"File không tồn tại: {safe_name}")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_name,
    )
