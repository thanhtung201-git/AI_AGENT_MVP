class POExtractionError(Exception):
    """Base exception class for all PO extraction related errors."""
    pass

class DataNormalizationError(POExtractionError):
    """Raised when raw data cannot be mapped or normalized to the required format."""
    pass

class BusinessValidationError(POExtractionError):
    """Raised when the extracted data violates a business rule (e.g., total quantities don't match)."""
    pass

class GroqAPIError(POExtractionError):
    """Raised when the Groq API fails to return a valid response."""
    pass
