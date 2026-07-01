"""
POST /api/agent/run — Upload file PO → AI trích xuất → tự tìm techpack → tạo trimlist.
Đây là luồng thống nhất, tương đương run_agent.py.
"""
import os
import glob
import logging
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from backend.agents.po_agent import POAgent
from backend.exporters.json_exporter import JsonExporter
from backend.exporters.excel_exporter import ExcelExporter
from backend.normalization.mapper import DataMapper
from backend.schemas.canonical import CanonicalSchema
from backend.database.supabase_client import SupabaseClient
from backend.extractors.trimlist_extractor import TrimlistExtractor
from backend.exporters.trimlist_exporter import TrimlistExporter
from tools.reader import read_file

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR  = "sample_data/uploads"
OUTPUT_DIR  = "sample_data"
TECHPACK_DIR = "Teck_pack"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _find_techpack(style_code: str) -> list:
    all_files = (
        glob.glob(f"{TECHPACK_DIR}/*.pdf") +
        glob.glob(f"{TECHPACK_DIR}/*.xlsx") +
        glob.glob(f"{TECHPACK_DIR}/*.docx")
    )
    if not all_files:
        return []
    if not style_code:
        return all_files

    style_lower = style_code.lower()
    by_name = [f for f in all_files if style_lower in os.path.basename(f).lower()]
    if by_name:
        return by_name

    by_content = []
    for f in all_files:
        try:
            r = read_file(f)
            if r["success"] and style_lower in r["text"].lower():
                by_content.append(f)
        except Exception:
            pass
    return by_content or all_files


@router.post("/run")
async def run_agent(file: UploadFile = File(...)):
    """
    Upload file PO → trích xuất PO → tự tìm techpack khớp → tạo trimlist.
    Trả về kết quả PO + trimlist + đường dẫn download.
    """
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in (".pdf", ".xlsx", ".xls"):
        raise HTTPException(400, "Chỉ hỗ trợ file PDF hoặc Excel (.pdf, .xlsx, .xls)")

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_path = os.path.join(UPLOAD_DIR, f"po_{timestamp}{ext}")
    contents   = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    # ── Bước 1-2: PO Agent ──────────────────────────────────────────────────
    try:
        agent  = POAgent()
        result = agent.process_request(
            user_request="Extract PO từ file và lưu vào database",
            file_path=saved_path,
        )
    except Exception as e:
        raise HTTPException(500, f"PO Agent lỗi: {e}")

    if result["status"] != "success":
        raise HTTPException(422, f"Trích xuất PO thất bại: {result.get('reason', 'Unknown')}")

    results = result.get("results", {})
    header  = results.get("header_extractor", {}).get("header", {})
    items   = results.get("item_extractor",  {}).get("items",  [])

    combined   = {**header, "items": items,
                  "total_quantity_all": sum(i.get("total_quantity") or 0 for i in items),
                  "total_amount":       sum(i.get("total_price")    or 0.0 for i in items)}
    normalized = DataMapper.map_po_data(combined)
    po_model   = CanonicalSchema.validate_and_load(normalized)

    # Export PO files
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
        logger.warning(f"Supabase bỏ qua: {e}")

    style_code  = po_model.items[0].style_code if po_model.items else ""
    order_qty   = po_model.total_quantity_all or sum(i.total_quantity or 0 for i in po_model.items)
    _item0      = po_model.items[0] if po_model.items else None
    style_name  = getattr(po_model, "style_name", "") or (getattr(_item0, "style_name", "") if _item0 else "")
    factory     = getattr(po_model, "factory", "") or ""

    po_data = {
        "po_id":        po_id,
        "po_number":    po_model.po_number,
        "style_code":   style_code,
        "style_name":   style_name,
        "buyer":        po_model.buyer,
        "factory":      factory,
        "total_qty":    order_qty,
        "total_amount": po_model.total_amount,
        "item_count":   len(po_model.items),
        "items":        [i.model_dump() for i in po_model.items],
        "excel_path":   excel_path,
    }

    # ── Bước 3: Tìm techpack & tạo trimlist ────────────────────────────────
    techpack_files = _find_techpack(style_code)
    if not techpack_files:
        return {
            "status":           "partial",
            "timestamp":        timestamp,
            "po":               po_data,
            "trimlist":         None,
            "techpack_found":   [],
            "warning":          f"Không tìm thấy file techpack trong thư mục '{TECHPACK_DIR}/'",
        }

    meta = {
        "po_number":   po_model.po_number  or "",
        "style_code":  style_code,
        "style_name":  style_name,
        "buyer":       po_model.buyer      or "",
        "order_qty":   f"{order_qty:,} pcs",
        "factory":     factory,
        "season":      getattr(po_model, "season", "") or "",
        "date":        datetime.now().strftime("%d/%m/%Y"),
        "prepared_by": "AI Agent",
    }

    extractor      = TrimlistExtractor()
    all_trim_items = []
    techpack_names = []

    for tp_path in techpack_files:
        techpack_names.append(os.path.basename(tp_path))
        r = read_file(tp_path)
        if not r.get("success"):
            logger.warning(f"Đọc techpack thất bại: {tp_path}")
            continue
        try:
            items_trim = extractor.extract(r["text"], order_qty=order_qty)
            for it in items_trim:
                it["_source_file"] = os.path.basename(tp_path)
            all_trim_items.extend(items_trim)
        except RuntimeError as e:
            if "RATE LIMIT" in str(e):
                raise HTTPException(429, str(e))
            logger.error(f"Trim extract lỗi: {e}")

    if not all_trim_items:
        return {
            "status":         "partial",
            "timestamp":      timestamp,
            "po":             po_data,
            "trimlist":       None,
            "techpack_found": techpack_names,
            "warning":        "Tìm thấy techpack nhưng không trích xuất được trim items (có thể hết quota API)",
        }

    # Dedup cross-file
    before = len(all_trim_items)
    all_trim_items = extractor._deduplicate(all_trim_items)
    if len(all_trim_items) < before:
        logger.info(f"Cross-file dedup: {before} → {len(all_trim_items)}")

    # Export trimlist Excel
    trim_dir  = os.path.join(OUTPUT_DIR, "trimlist")
    os.makedirs(trim_dir, exist_ok=True)
    trim_path = os.path.join(trim_dir, f"trimlist_{timestamp}.xlsx")
    TrimlistExporter.export(trim_items=all_trim_items, output_path=trim_path, meta=meta)

    return {
        "status":           "success",
        "timestamp":        timestamp,
        "po":               po_data,
        "techpack_found":   techpack_names,
        "trimlist": {
            "item_count": len(all_trim_items),
            "trim_items": all_trim_items,
            "excel_path": trim_path,
        },
    }


@router.get("/download/po/{timestamp}")
def download_po(timestamp: str):
    path = os.path.join(OUTPUT_DIR, f"output_po_{timestamp}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"PO_{timestamp}.xlsx")


@router.get("/download/trimlist/{timestamp}")
def download_trimlist(timestamp: str):
    path = os.path.join(OUTPUT_DIR, f"trimlist/trimlist_{timestamp}.xlsx")
    if not os.path.exists(path):
        raise HTTPException(404, "File không tồn tại")
    return FileResponse(path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"Trimlist_{timestamp}.xlsx")
