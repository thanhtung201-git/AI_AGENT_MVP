"""
Demo: Tên cột hoàn toàn KHÔNG có trong code — Regex vs LLM
"""
import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.extractors.header_extractor import HeaderExtractor

# Tên cột kỳ lạ, không ai đoán trước được — không có trong bất kỳ dòng code nào
PO_WEIRD = """
PROCUREMENT DOCUMENT
Ref Code      : REF-2024-999
Purchasing Org: MEGA FASHION GROUP       <- không phải Buyer/Customer/Client
Fulfiller     : THREAD & NEEDLE CO.      <- không phải Seller/Vendor/Supplier
Raised On     : 05-APR-2024              <- không phải Order Date/Issue Date
Expected By   : 20-APR-2024

LINE ITEMS
Article No    : ART-88001
Article Name  : Premium Wool Blazer
Unit Rate     : 320.00                   <- không phải Price/Cost/Đơn giá
Pcs           : 150                      <- không phải QTY/Units/Số lượng
Colorway      : CHARCOAL GREY            <- không phải Colour/Color/Màu
Line Value    : 48000.00                 <- không phải Total/Amount/Thành tiền
"""

header_extractor = HeaderExtractor()

print("=" * 60)
print("  INPUT: Tên cột HOÀN TOÀN không có trong code")
print("=" * 60)
print(PO_WEIRD)

print("=" * 60)
print("  CÁCH 1: Regex cứng (mô phỏng logic run.py cũ)")
print("=" * 60)

# Regex chỉ biết tìm đúng các pattern đã hardcode
KNOWN_PATTERNS = {
    "po_number":  r"(?:PO No|PO Number|Purchase Order #|PO #)[:\s]+(\S+)",
    "buyer":      r"(?:Buyer|Customer|Client|Đơn vị mua)[:\s]+(.+)",
    "seller":     r"(?:Seller|Vendor|Supplier|Nhà cung cấp)[:\s]+(.+)",
    "order_date": r"(?:Order Date|Issue Date|Ngày lập)[:\s]+(.+)",
}

for field, pattern in KNOWN_PATTERNS.items():
    m = re.search(pattern, PO_WEIRD, re.IGNORECASE)
    val = m.group(1).strip() if m else "❌ KHÔNG TÌM THẤY"
    print(f"  {field:12}: {val}")

print()
print("  → Regex mất sạch dữ liệu vì không biết:")
print("    'Purchasing Org', 'Fulfiller', 'Raised On', 'Ref Code'")

print()
print("=" * 60)
print("  CÁCH 2: LLM Extractor (agent)")
print("=" * 60)

result = header_extractor.extract(PO_WEIRD)

fields = ["po_number", "buyer", "seller", "order_date", "delivery_date"]
for f in fields:
    val = result.get(f) or "null"
    icon = "✅" if result.get(f) else "—"
    print(f"  {icon} {f:15}: {val}")
