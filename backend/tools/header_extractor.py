from typing import Dict, Any
from backend.tools.base import BaseTool
from backend.extractors.header_extractor import HeaderExtractor


class HeaderExtractorTool(BaseTool):
    name = "header_extractor"
    description = "Extracts PO header fields like vendor, buyer, and date."

    def __init__(self):
        self._extractor = HeaderExtractor()

    def execute(self, **kwargs) -> Dict[str, Any]:
        text = kwargs.get("text")
        if not text:
            return {"error": "text is required", "success": False}

        try:
            header = self._extractor.extract(text)
            return {"header": header, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}
