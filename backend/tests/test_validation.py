import unittest
from backend.schemas.po_schema import POData, POItem
from backend.validation.engine import ValidationEngine
from backend.exceptions.errors import BusinessValidationError
from backend.normalization.mapper import DataMapper

class TestValidationEngine(unittest.TestCase):
    def test_validation_passes(self):
        """Test that a valid PO passes business rules."""
        item = POItem(style_code="A", total_quantity=100, unit_price=5.0, total_price=500.0, size_breakdown={"S": 50, "M": 50})
        po = POData(items=[item])
        self.assertTrue(ValidationEngine.validate(po))
        
    def test_validation_fails_size_sum(self):
        """Test that incorrect size sum raises an error."""
        item = POItem(style_code="A", total_quantity=100, size_breakdown={"S": 50, "M": 40}) # Sum is 90
        po = POData(items=[item])
        with self.assertRaises(BusinessValidationError):
            ValidationEngine.validate(po)
            
    def test_validation_fails_total_price(self):
        """Test that incorrect total price raises an error."""
        item = POItem(style_code="A", total_quantity=100, unit_price=5.0, total_price=400.0) # Should be 500
        po = POData(items=[item])
        with self.assertRaises(BusinessValidationError):
            ValidationEngine.validate(po)

class TestDataMapper(unittest.TestCase):
    def test_normalize_currency(self):
        self.assertEqual(DataMapper.normalize_currency(" usd "), "USD")
        self.assertEqual(DataMapper.normalize_currency(None), "USD")

if __name__ == '__main__':
    unittest.main()
