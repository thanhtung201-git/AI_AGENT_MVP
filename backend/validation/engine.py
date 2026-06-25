from backend.schemas.po_schema import POData
from backend.exceptions.errors import BusinessValidationError
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)

class ValidationEngine:
    """
    Applies business logic rules to the Canonical Schema.
    """
    
    @staticmethod
    def validate(po_data: POData) -> bool:
        logger.info("Running Business Rule Validation Engine...")
        errors = []
        
        for idx, item in enumerate(po_data.items):
            # Rule 1: Size breakdown sum must equal total_quantity
            if item.size_breakdown:
                calculated_sum = sum(item.size_breakdown.values())
                if item.total_quantity is not None and calculated_sum != item.total_quantity:
                    err_msg = f"Item {item.style_code}: Size sum ({calculated_sum}) != total_quantity ({item.total_quantity})"
                    errors.append(err_msg)
            
            # Rule 2: Unit Price * Total Quantity = Total Price
            if item.unit_price and item.total_quantity:
                expected_total = item.unit_price * item.total_quantity
                # Using a small tolerance for float comparison
                if item.total_price is not None and abs(expected_total - item.total_price) > 0.01:
                    err_msg = f"Item {item.style_code}: Calculated total price ({expected_total}) != extracted total price ({item.total_price})"
                    errors.append(err_msg)
                    
        if errors:
            for error in errors:
                logger.error(f"Validation Failure: {error}")
            raise BusinessValidationError(f"PO failed business validation with {len(errors)} errors. Check logs for details.")
            
        logger.info("Business validation passed successfully.")
        return True
