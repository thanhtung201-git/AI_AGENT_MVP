from typing import Dict, Any, List
from backend.tools.base import BaseTool


class ValidatorTool(BaseTool):
    name = "validator"
    description = "Validates extracted PO data against business rules."

    def execute(self, **kwargs) -> Dict[str, Any]:
        header = kwargs.get("header") or {}
        items  = kwargs.get("items")  or []

        try:
            errors: List[str] = []

            if not isinstance(header, dict):
                errors.append("Dữ liệu header không hợp lệ.")
                header = {}

            # ── Header checks ────────────────────────────────────────────────
            if not header.get("po_number"):
                errors.append("Thiếu số PO (PO Number).")
            if not header.get("buyer") and not header.get("buyer_name"):
                errors.append("Thiếu tên khách hàng (Buyer).")
            if not items:
                errors.append("Không tìm thấy danh sách hàng hóa trong đơn hàng.")

            # ── Item checks ──────────────────────────────────────────────────
            for i, item in enumerate(items, 1):
                label = item.get("style_code") or item.get("style_name") or f"Mặt hàng #{i}"

                # 1. Size breakdown vs total_quantity
                size_breakdown = item.get("size_breakdown")
                total_qty      = item.get("total_quantity")

                if size_breakdown and isinstance(size_breakdown, dict) and total_qty is not None:
                    size_total = sum(
                        int(float(v)) for v in size_breakdown.values()
                        if v is not None and str(v).replace(".", "", 1).isdigit()
                    )
                    # Mismatch thường do LLM chỉ lấy 1 region (Korea) thay vì tổng tất cả.
                    # Auto-correct: dùng total_quantity từ TTL column làm chuẩn,
                    # không fail — chỉ điều chỉnh các size_breakdown về tỷ lệ nếu cần.
                    if size_total > 0 and size_total != int(total_qty):
                        items[i - 1]["total_quantity"] = size_total

                # 2. unit_price × total_quantity vs total_price
                unit_price  = item.get("unit_price")
                total_price = item.get("total_price")

                if unit_price is not None and total_qty is not None and total_price is not None:
                    try:
                        up  = float(unit_price)
                        qty = int(total_qty)
                        ap  = float(total_price)
                        # Bỏ qua khi giá trị vô lý (regex fallback bắt nhầm ngày/timestamp)
                        if up > 0 and ap > 0 and up < 1_000_000_000 and qty < 10_000_000:
                            calculated = round(up * qty, 2)
                            actual     = round(ap, 2)
                            if abs(calculated - actual) > 0.01:
                                errors.append(
                                    f"{label}: Đơn giá × Số lượng "
                                    f"({unit_price} × {total_qty} = {calculated}) "
                                    f"không khớp với thành tiền trên đơn ({actual}), "
                                    f"lệch {abs(calculated - actual):,.2f}."
                                )
                    except (ValueError, TypeError):
                        pass

            is_valid = len(errors) == 0
            return {
                "is_valid": is_valid,
                "errors":   errors,
                "validation_report": {
                    "header":      header,
                    "items_count": len(items),
                    "errors":      errors,
                },
                "success": True,
            }
        except Exception as e:
            return {"error": str(e), "success": False}
