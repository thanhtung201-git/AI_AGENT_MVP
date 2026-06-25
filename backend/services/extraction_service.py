import logging
from backend.extractors.header_extractor import HeaderExtractor
from backend.extractors.item_extractor import ItemExtractor
from backend.extractors.size_extractor import SizeExtractor
from backend.extractors.shipping_extractor import ShippingExtractor
from backend.schemas.po_schema import POData

logger = logging.getLogger(__name__)

class ExtractionService:
    """
    Orchestrates the various extractors to build the complete POData.
    This fulfills the 'Day 6: Testing / Integration' phase.
    """
    
    def __init__(self):
        self.header_extractor = HeaderExtractor()
        self.item_extractor = ItemExtractor()
        self.size_extractor = SizeExtractor()
        self.shipping_extractor = ShippingExtractor()

    def process_po(self, raw_text: str) -> POData:
        """Runs the multi-stage extraction and validates against the Pydantic schema."""
        logger.info("Starting PO extraction pipeline...")
        
        # Stage 1: Header
        header_data = self.header_extractor.extract(raw_text)
        
        # Stage 2: Shipping & Notes
        shipping_data = self.shipping_extractor.extract(raw_text)
        
        # Stage 3: Items
        items_data = self.item_extractor.extract(raw_text)
        items_list = items_data.get("items", [])
        
        # Stage 4: Size Breakdown for each item
        for item in items_list:
            style_code = item.get("style_code")
            if style_code:
                size_data = self.size_extractor.extract(raw_text, style_code)
                item["size_breakdown"] = size_data.get("size_breakdown", {})
        
        # Combine everything into a single dictionary
        combined_data = {
            **header_data,
            **shipping_data,
            "items": items_list
        }
        
        # Calculate totals if they are missing
        total_qty = 0
        total_amt = 0.0
        for item in items_list:
            qty = item.get("total_quantity") or 0
            price = item.get("total_price") or 0.0
            total_qty += qty
            total_amt += price
            
        combined_data["total_quantity_all"] = total_qty
        combined_data["total_amount"] = total_amt

        # Data Normalization
        from backend.normalization.mapper import DataMapper
        from backend.schemas.canonical import CanonicalSchema
        from backend.validation.engine import ValidationEngine
        
        normalized_data = DataMapper.map_po_data(combined_data)

        # Validate and return Pydantic model (Canonical Schema)
        po_model = CanonicalSchema.validate_and_load(normalized_data)
        
        # Business Rule Validation
        ValidationEngine.validate(po_model)
        
        logger.info("Extraction and Validation complete successfully.")
        return po_model
