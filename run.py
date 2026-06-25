import os
import sys
from tools.reader import read_file
from backend.services.extraction_service import ExtractionService
from backend.exporters.json_exporter import JsonExporter
from backend.exporters.excel_exporter import ExcelExporter

from backend.config.settings import settings

if __name__ == "__main__":
    # Ensure GROQ_API_KEY is set
    if not settings.GROQ_API_KEY:
        print("[ERROR] Ban chua cau hinh GROQ_API_KEY. Vui long them no vao bien moi truong.")
        print('Vi du tren Windows: set GROQ_API_KEY="your-api-key"')
        sys.exit(1)

    file_can_doc = "sample_data/test_po.pdf" # Dung file test_po.pdf hoac file nao ban co trong sample_data
    
    if not os.path.exists(file_can_doc):
        # Fallback to the excel file mentioned in previous run.py if pdf doesn't exist
        file_can_doc = "sample_data/processed_po.xlsx"
        if not os.path.exists(file_can_doc):
            print(f"[ERROR] Khong tim thay file du lieu mau nao de chay test.")
            sys.exit(1)

    print(f"[INFO] Dang doc file: {file_can_doc}...")
    result = read_file(file_can_doc)

    if result["success"]:
        print(f"[SUCCESS] Doc thanh cong | Dinh dang: {result['format']}")
        raw_text = result["text"]
        
        print(f"[INFO] Dang goi AI Extraction Engine de trich xuat du lieu...")
        try:
            service = ExtractionService()
            po_data = service.process_po(raw_text)
            
            # Export data
            json_path = "sample_data/output_po.json"
            excel_path = "sample_data/output_po.xlsx"
            
            JsonExporter.export(po_data, json_path)
            ExcelExporter.export(po_data, excel_path)
            
            print(f"[SUCCESS] Hoan tat! Du lieu da duoc trich xuat va luu tai:")
            print(f"  - JSON: {json_path}")
            print(f"  - Excel: {excel_path}")
            
        except Exception as e:
            print(f"[ERROR] Loi trong qua trinh trich xuat/Validation: {e}")
            
    else:
        print(f"[ERROR] Loi doc file: {result['error']}")