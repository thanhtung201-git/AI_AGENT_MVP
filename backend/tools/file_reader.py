from typing import Dict, Any
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.tools.base import BaseTool
from tools.reader import read_file


class FileReaderTool(BaseTool):
    name = "file_reader"
    description = "Reads and extracts text from any file: PDF, PDF scan, Excel, Word, Image, Email."

    def execute(self, **kwargs) -> Dict[str, Any]:
        file_path = kwargs.get("file_path")
        if not file_path:
            return {"error": "file_path is required", "success": False}
        try:
            result = read_file(file_path)
            if result.get("success"):
                return {"text": result["text"], "format": result["format"], "success": True}
            return {"error": result.get("error"), "success": False}
        except Exception as e:
            return {"error": str(e), "success": False}

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        }
