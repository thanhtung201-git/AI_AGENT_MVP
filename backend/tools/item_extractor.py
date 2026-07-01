from typing import Dict, Any
from backend.tools.base import BaseTool
from backend.extractors.item_extractor import ItemExtractor


class ItemExtractorTool(BaseTool):
    name = "item_extractor"
    description = "Extracts line items from PO text."

    def __init__(self):
        self._extractor = ItemExtractor()

    def execute(self, **kwargs) -> Dict[str, Any]:
        text = kwargs.get("text")
        if not text:
            return {"error": "text is required", "success": False}
        try:
            items = self._extractor.extract(text)
            if not items:
                return {"error": "Item extraction returned empty result", "success": False}
            return {"items": items, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}