import json
import os
from backend.schemas.po_schema import POData

class JsonExporter:
    """Exports POData to a JSON file."""
    
    @staticmethod
    def export(po_data: POData, output_path: str):
        # Convert Pydantic model to dict, excluding None values if preferred
        data_dict = po_data.model_dump()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=4)
