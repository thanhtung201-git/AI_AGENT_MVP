"""
Demo: Sự khác biệt giữa run.py (pipeline cứng) vs run_agent.py (agent retry)
Kịch bản: item_extractor trả về lỗi ở lần gọi đầu tiên (giả lập rate limit / JSON lỗi)
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Giả lập extractor KHÔNG ổn định (fail lần 1, pass lần 2+) ────────────────
_call_count = 0

def unstable_item_extractor(text: str):
    global _call_count
    _call_count += 1
    if _call_count == 1:
        raise Exception("Rate limit 429: Too Many Requests")  # lỗi thật từ Groq
    # Lần 2 trở đi: thành công
    return [
        {"style_code": "99880052", "style_name": "Poshmark black dress",
         "total_quantity": 1, "unit_price": 1080.0, "total_price": 1080.0},
    ]

HEADER = {"po_number": "123456/22", "buyer": "FASHION QUEEN"}
RAW_TEXT = "sample PO text..."


# ════════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("  CÁCH 1: run.py — Pipeline cứng, KHÔNG retry")
print("=" * 60)

_call_count = 0  # reset
try:
    header = HEADER
    items = unstable_item_extractor(RAW_TEXT)   # ← crash ngay lần đầu
    print(f"  Header : {header['po_number']}")
    print(f"  Items  : {len(items)} dòng hàng")
    print("  [SUCCESS]")
except Exception as e:
    print(f"  [ERROR] Lỗi: {e}")
    print("  → Dừng hẳn. Không có output JSON/Excel nào được tạo ra.")


# ════════════════════════════════════════════════════════════════════════════════
print()
print("=" * 60)
print("  CÁCH 2: run_agent.py — Agent tự retry")
print("=" * 60)

_call_count = 0  # reset
MAX_RETRIES = 3
items = None

for attempt in range(1, MAX_RETRIES + 1):
    print(f"\n  --- Lần thử {attempt}/{MAX_RETRIES} ---")
    try:
        header = HEADER
        items = unstable_item_extractor(RAW_TEXT)

        # Reviewer đánh giá
        confidence = 1.0
        print(f"  ✓ header_extractor : OK")
        print(f"  ✓ item_extractor   : {len(items)} items")
        print(f"  ✓ validator        : PASS")
        print(f"  ✓ Reviewer         : PASS (score={confidence})")
        print(f"\n  [SUCCESS] Hoàn tất ở lần thử {attempt}!")
        print(f"  → Xuất file JSON + Excel thành công.")
        break

    except Exception as e:
        print(f"  ✗ item_extractor   : FAIL — {e}")
        print(f"  ✗ Reviewer         : FAIL — thiếu items, sẽ retry...")
        if attempt == MAX_RETRIES:
            print(f"\n  [FAILED] Đã thử {MAX_RETRIES} lần, vẫn không thành công.")
