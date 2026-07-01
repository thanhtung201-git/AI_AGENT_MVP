from typing import Dict, Any
from backend.tools.base import BaseTool

class ValidatorTool(BaseTool):
    name = "validator"
    description = "Validates extracted PO data against business rules."

    def execute(self, **kwargs) -> Dict[str, Any]:
        header = kwargs.get("header") or {}
        items = kwargs.get("items") or []

        try:
            errors = []

            if not isinstance(header, dict):
                errors.append("header must be a dict.")
                header = {}

            if not header.get("po_number"):
                errors.append("PO number is missing.")
            if not header.get("buyer") and not header.get("buyer_name"):
                errors.append("Buyer is missing.")
            if not items:
                errors.append("No line items found.")

            is_valid = len(errors) == 0
            return {
                "is_valid": is_valid,
                "errors": errors,
                "validation_report": {
                    "header": header,
                    "items_count": len(items),
                    "errors": errors,
                },
                "success": True,
            }
        except Exception as e:
            return {"error": str(e), "success": False}
