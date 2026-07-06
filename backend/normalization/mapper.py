from typing import Dict, Any
from datetime import datetime
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)

class DataMapper:
    """
    Mapping Layer: Cleans and normalizes raw AI strings before validation.
    Converts dates, standardizes currencies, strips whitespace, etc.
    """
    
    @staticmethod
    def normalize_date(date_str: str) -> str:
        """Attempts to normalize date to YYYY-MM-DD."""
        if not date_str:
            return None
        # Basic cleanup
        date_str = date_str.strip()
        # Complex date parsing could be added here using dateutil
        return date_str

    @staticmethod
    def normalize_currency(currency_str: str) -> str:
        """Standardizes currency codes to uppercase."""
        if not currency_str:
            return "USD" # Default
        return currency_str.strip().upper()

    @staticmethod
    def map_po_data(raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Runs the entire dictionary through normalization rules."""
        logger.info("Starting Data Normalization mapping.")
        
        # Normalize Header Dates
        for date_field in ["order_date", "delivery_date", "ship_date"]:
            if date_field in raw_data:
                raw_data[date_field] = DataMapper.normalize_date(raw_data[date_field])
                
        # Normalize Currency
        if "currency" in raw_data:
            raw_data["currency"] = DataMapper.normalize_currency(raw_data["currency"])
            
        # Clean Item string fields
        for item in raw_data.get("items", []):
            if item.get("style_code"):
                item["style_code"] = str(item["style_code"]).strip().upper()
            if item.get("color_code"):
                item["color_code"] = str(item["color_code"]).strip().upper()

        return raw_data
