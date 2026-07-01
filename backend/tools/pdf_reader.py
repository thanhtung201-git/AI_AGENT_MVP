from typing import Dict, Any
from backend.tools.base import BaseTool
import os
import sys

# Add root to sys path to allow importing existing modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from tools.pdf_reader import read_pdf

class PDFReaderTool(BaseTool):
    name = "pdf_reader"
    description = "Reads and extracts text from a PDF file."
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs.get("file_path")
        if not file_path:
            return {"error": "file_path is required", "success": False}
            
        try:
            # Reusing existing read_pdf logic
            result = read_pdf(file_path)
            if result.get("success"):
                return {"text": result.get("text"), "success": True}
            else:
                return {"error": result.get("error"), "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}
            
    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"}
            },
            "required": ["file_path"]
        }
