"""
Demo: Agent có thể nhận ra cùng dữ liệu nhưng khác tên cột không?
So sánh: Regex (cứng) vs LLM extractor (linh hoạt)
"""
import sys, io, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from backend.extractors.header_extractor import HeaderExtractor
from backend.extractors.item_extractor import ItemExtractor

# ── 3 phiên bản PO cùng dữ liệu, khác tên cột ────────────────────────────────

PO_STANDARD = """
--- DỮ LIỆU TỪ Ô FORM ĐIỀN SẴN ---
Text1: 123456/22
Text3: FASHION QUEEN
Text2: 22ND SEPTEMBER, 2022
Text7: FASHION ITEMS INC
Text11: Poshmark black dress
Text12: 99880052
Text13: 1080
Text14: 1
Text15: M
Text16: BLACK
Text17: 1080
"""

PO_ALIAS_EN = """
PURCHASE ORDER
PO No     : PO-9988
Customer  : ZARA VIETNAM          <- "Customer" thay vì "Buyer"
Vendor    : TEXTILE CORP          <- "Vendor" thay vì "Seller"
Issue Date: 01/03/2024            <- "Issue Date" thay vì "Order Date"
Due Date  : 15/03/2024            <- "Due Date" thay vì "Delivery Date"

PRODUCT LIST                      <- "Product List" thay vì "Order Information"
SKU       : ZR-2024-001           <- "SKU" thay vì "Item #"
Desc      : Slim Fit Chino Pants  <- "Desc" thay vì "Product Name"
Cost      : 25.50                 <- "Cost" thay vì "Price"
Units     : 200                   <- "Units" thay vì "QTY"
Colour    : NAVY BLUE
Amount    : 5100.00               <- "Amount" thay vì "Total"
"""

PO_ALIAS_VI = """
ĐƠN ĐẶT HÀNG
Số PO        : DH-2024-007
Đơn vị mua   : CÔNG TY MAY MẶC ABC     <- tiếng Việt
Nhà cung cấp : XƯỞNG DỆT XYZ
Ngày lập     : 10/06/2024
Ngày giao    : 30/06/2024

DANH SÁCH HÀNG HÓA
Mã sản phẩm  : SP-001
Tên hàng     : Áo sơ mi nam dài tay
Đơn giá      : 150,000 VND
Số lượng     : 500
Màu sắc      : TRẮNG
Thành tiền   : 75,000,000 VND
"""

header_extractor = HeaderExtractor()
item_extractor   = ItemExtractor()

cases = [
    ("PO chuẩn (form fields)",          PO_STANDARD),
    ("PO tiếng Anh — tên cột khác",     PO_ALIAS_EN),
    ("PO tiếng Việt — tên cột khác",    PO_ALIAS_VI),
]

for title, text in cases:
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)

    header = header_extractor.extract(text)
    items  = item_extractor.extract(text)

    print(f"  po_number : {header.get('po_number')}")
    print(f"  buyer     : {header.get('buyer')}")
    print(f"  seller    : {header.get('seller')}")
    print(f"  order_date: {header.get('order_date')}")
    print(f"  Items ({len(items)}):")
    for it in items:
        print(f"    - [{it.get('style_code')}] {it.get('style_name')} | "
              f"qty={it.get('total_quantity')} | price={it.get('unit_price')}")
    print()
