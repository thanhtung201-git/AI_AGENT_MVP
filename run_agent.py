"""
AI Agent — Luồng thống nhất:
  Bước 1-2: Đọc PO → trích xuất header + items → export JSON + Excel + lưu Supabase
  Bước 3  : Tự tìm techpack khớp style_code → trích xuất trim → export Trimlist Excel
"""
import os
import sys
import json
import glob
import logging
import io
from datetime import datetime
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from backend.config.settings import settings
from backend.agents.po_agent import POAgent
from backend.exporters.json_exporter import JsonExporter
from backend.exporters.excel_exporter import ExcelExporter
from backend.normalization.mapper import DataMapper
from backend.schemas.canonical import CanonicalSchema
from backend.database.supabase_client import SupabaseClient
from backend.extractors.trimlist_extractor import TrimlistExtractor
from backend.exporters.trimlist_exporter import TrimlistExporter
from tools.reader import read_file


# ══════════════════════════════════════════════════════════
#  BƯỚC 1-2: XỬ LÝ PO
# ══════════════════════════════════════════════════════════

def run_po_agent(file_path: str) -> tuple:
    """Chạy PO Agent, trả về (po_model, agent_result, timestamp)."""
    user_request = "Extract PO từ file và lưu vào database"

    print("=" * 55)
    print("  BƯỚC 1-2 — Đọc PO & Trích xuất dữ liệu")
    print("=" * 55)
    print(f"  File: {file_path}\n")

    agent  = POAgent()
    result = agent.process_request(user_request=user_request, file_path=file_path)

    print("\n=== Lịch sử thực thi ===")
    for step in result["history"]:
        action = step.get("action", "")
        if action == "plan":
            print(f"  Lần {step.get('attempt')}: Plan → {step.get('steps')}")
        elif action == "execute_tool":
            icon = "✓" if step.get("success") else "✗"
            print(f"  {icon} Tool: {step.get('tool')}")
        elif action == "reflect":
            print(f"  Review: {step.get('verdict')} (score={step.get('confidence_score')})")

    if result["status"] != "success":
        print(f"\n[FAILED] {result.get('reason')}")
        return None, result, None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results   = result.get("results", {})
    header    = results.get("header_extractor", {}).get("header", {})
    items     = results.get("item_extractor", {}).get("items", [])

    combined = {
        **header,
        "items": items,
        "total_quantity_all": sum(i.get("total_quantity") or 0 for i in items),
        "total_amount":       sum(i.get("total_price") or 0.0 for i in items),
    }
    normalized = DataMapper.map_po_data(combined)
    po_model   = CanonicalSchema.validate_and_load(normalized)

    # Export PO
    os.makedirs("sample_data", exist_ok=True)
    json_path  = f"sample_data/output_po_{timestamp}.json"
    excel_path = f"sample_data/output_po_{timestamp}.xlsx"
    JsonExporter.export(po_model, json_path)
    ExcelExporter.export(po_model, excel_path)

    _style = po_model.items[0].style_code if po_model.items else "N/A"
    _qty   = po_model.total_quantity_all or sum(i.total_quantity or 0 for i in po_model.items)
    print(f"\n[SUCCESS] PO trích xuất xong:")
    print(f"  - PO Number : {po_model.po_number or 'N/A'}")
    print(f"  - Style     : {_style}")
    print(f"  - Buyer     : {po_model.buyer or 'N/A'}")
    print(f"  - Order Qty : {_qty:,} pcs")
    print(f"  - JSON      : {json_path}")
    print(f"  - Excel     : {excel_path}")

    # Lưu Supabase
    try:
        db    = SupabaseClient()
        po_id = db.insert_po(header=header, items=items)
        if po_id:
            print(f"  - Supabase  : id={po_id} ({len(items)} items)")
    except Exception as e:
        print(f"  - Supabase  : bỏ qua ({e})")

    return po_model, result, timestamp


# ══════════════════════════════════════════════════════════
#  BƯỚC 3: TÌM TECHPACK & TẠO TRIMLIST
# ══════════════════════════════════════════════════════════

def find_techpack(style_code: str, techpack_dir: str = "Teck_pack") -> list:
    """
    Tự động tìm techpack khớp với style_code từ PO.
    Ưu tiên: tên file chứa style_code → nội dung file chứa style_code → tất cả file.
    """
    all_files = (
        glob.glob(f"{techpack_dir}/*.pdf") +
        glob.glob(f"{techpack_dir}/*.xlsx") +
        glob.glob(f"{techpack_dir}/*.docx")
    )
    if not all_files:
        return []

    if not style_code:
        return all_files

    style_lower = style_code.lower()

    # Lớp 1: tên file chứa style_code
    by_name = [f for f in all_files if style_lower in os.path.basename(f).lower()]
    if by_name:
        return by_name

    # Lớp 2: nội dung file chứa style_code
    by_content = []
    for f in all_files:
        try:
            r = read_file(f)
            if r["success"] and style_lower in r["text"].lower():
                by_content.append(f)
        except Exception:
            pass
    if by_content:
        return by_content

    # Lớp 3: fallback — dùng tất cả file trong thư mục
    print(f"  [INFO] Không tìm thấy techpack khớp '{style_code}', dùng tất cả file.")
    return all_files


def run_trimlist(po_model, timestamp: str):
    """Tìm techpack → trích xuất trim → export Trimlist Excel."""
    print("\n" + "=" * 55)
    print("  BƯỚC 3 — Tìm Techpack & Tạo Trimlist")
    print("=" * 55)

    # style_code và total_quantity nằm trong items, không phải root POData
    style_code = ""
    if po_model.items:
        style_code = po_model.items[0].style_code or ""

    order_qty = po_model.total_quantity_all or 0
    if not order_qty and po_model.items:
        order_qty = sum(i.total_quantity or 0 for i in po_model.items)

    print(f"  Style Code : {style_code}")
    print(f"  Order Qty  : {order_qty:,} pcs")
    print(f"\n  Đang tìm techpack khớp...")

    techpack_files = find_techpack(style_code)
    if not techpack_files:
        print("  [WARNING] Không tìm thấy file techpack trong thư mục 'Teck_pack/'.")
        print("            Bỏ qua bước tạo Trimlist.")
        return None

    print(f"  Tìm thấy {len(techpack_files)} techpack:")
    for f in techpack_files:
        print(f"    - {f}")

    extractor = TrimlistExtractor()

    # Meta từ PO — style_name lấy từ items[0], factory từ root POData (added to schema)
    _item0      = po_model.items[0] if po_model.items else None
    _style_name = getattr(po_model, "style_name", "") or (getattr(_item0, "style_name", "") if _item0 else "")
    _factory    = getattr(po_model, "factory", "") or ""

    meta = {
        "po_number":   po_model.po_number   or "",
        "style_code":  style_code,
        "style_name":  _style_name,
        "buyer":       po_model.buyer        or "",
        "order_qty":   f"{order_qty:,} pcs",
        "factory":     _factory,
        "season":      getattr(po_model, "season", "") or "",
        "date":        datetime.now().strftime("%d/%m/%Y"),
        "prepared_by": "AI Agent",
    }

    # Trích xuất trim từ các techpack tìm được
    all_trim_items = []
    for file_path in techpack_files:
        print(f"\n  [INFO] Đang xử lý: {file_path}")
        r = read_file(file_path)
        if not r["success"]:
            print(f"    [WARNING] Đọc thất bại: {r['error']}")
            continue

        print(f"    Đọc thành công ({len(r['text'])} ký tự) — {r['format']}")
        print(f"    Đang gọi LLM trích xuất trim...")

        items = extractor.extract(r["text"], order_qty=order_qty)
        print(f"    → {len(items)} trim items")

        for it in items:
            it["_source_file"] = os.path.basename(file_path)
        all_trim_items.extend(items)

    if not all_trim_items:
        print("\n  [WARNING] Không trích xuất được trim nào.")
        return None

    # Dedup lần cuối sau khi gộp từ tất cả techpack files
    before = len(all_trim_items)
    all_trim_items = extractor._deduplicate(all_trim_items)
    if len(all_trim_items) < before:
        print(f"\n  [INFO] Cross-file dedup: {before} → {len(all_trim_items)} items")

    # Export Excel Trimlist
    output_dir  = "sample_data/trimlist"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/trimlist_{timestamp}.xlsx"

    TrimlistExporter.export(
        trim_items=all_trim_items,
        output_path=output_path,
        meta=meta,
    )

    print(f"\n[SUCCESS] Trimlist đã được tạo:")
    print(f"  - Excel : {output_path}")
    print(f"  - Tổng  : {len(all_trim_items)} trim items")
    print(f"\n  {'No.':<4} {'Trim Item':<28} {'Supplier':<20} {'Qty/Pc':<8} {'Total Qty'}")
    print(f"  {'-'*75}")
    for i, it in enumerate(all_trim_items, 1):
        total = f"{it['total_qty']:,.0f}" if it.get("total_qty") else "—"
        print(f"  {i:<4} {str(it.get('trim_item','')):<28} "
              f"{str(it.get('supplier','')):<20} "
              f"{str(it.get('qty_per_garment','')):<8} {total}")

    return output_path


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

def main():
    if not settings.GROQ_API_KEY:
        print("[ERROR] Chưa cấu hình GROQ_API_KEY.")
        sys.exit(1)

    # Input PO — đổi đường dẫn này khi chạy file khác
    file_path = r"C:\MCNA\P95-Duan_congty_maymac\ai_agent_mvp\sample_data\test_po_techpack.pdf"

    if not os.path.exists(file_path):
        print(f"[ERROR] Không tìm thấy file: {file_path}")
        sys.exit(1)

    # ── Bước 1-2: PO Agent ──────────────────────────────
    po_model, _, timestamp = run_po_agent(file_path)

    if po_model is None:
        print("\n[ERROR] PO Agent thất bại, dừng lại.")
        sys.exit(1)

    # ── Bước 3: Trimlist ────────────────────────────────
    try:
        run_trimlist(po_model, timestamp)
    except RuntimeError as e:
        if "RATE LIMIT" in str(e):
            print(f"\n[WARNING] {e}")
            print("  Trimlist sẽ được tạo sau khi quota reset.")
        else:
            print(f"\n[WARNING] Trimlist thất bại: {e}")

    print("\n" + "=" * 55)
    print("  Hoàn tất toàn bộ luồng xử lý.")
    print("=" * 55)


if __name__ == "__main__":
    main()
