"""
po_parser — Deterministic, structure-based PO parser (no hardcoded positions).

Detects garment-order structure from SEMANTIC/STRUCTURAL signals — which column
holds article codes, which rows are size headers, which columns are size vs
subtotal — instead of fixed row/column indices, sheet names, or size/color names.

Modules (single responsibility each):
  grid.py       — GridSheet: dense matrix with merged-cell expansion
  structure.py  — StructureDetector: locate header band + classify columns
  parser.py     — POParser: iterate blocks → CanonicalOrder
  validator.py  — POValidator: business-rule checks before GO generation
"""
from backend.go_compare.po_parser.parser import POParser
from backend.go_compare.po_parser.validator import POValidator, ValidationIssue

__all__ = ["POParser", "POValidator", "ValidationIssue"]
