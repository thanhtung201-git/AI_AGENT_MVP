from backend.schemas.po_schema import POData, POItem

# For Day 2 Canonical Schema, we are alias importing our solid POData model.
# POData already acts as the Canonical representation.
# This file serves as the strict boundary between normalized dicts and the domain object.

class CanonicalSchema:
    @staticmethod
    def validate_and_load(normalized_data: dict) -> POData:
        """
        Converts a normalized dictionary into the Canonical POData object.
        Pydantic handles basic type validation here.
        """
        return POData(**normalized_data)
