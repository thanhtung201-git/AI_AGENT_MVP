"""
go_compare — PO ↔ GO comparison pipeline (LLM-driven, brand-agnostic).

Flow:
  1. DocumentReader   — LLM reads any PO doc → CanonicalOrder (with traceability)
  2. BatchGOGenerator — deterministic Python → Batch_GO_Output.xlsx
  3. DocumentReader   — LLM reads the generated Batch GO back → CanonicalOrder (GO)
  4. CompareEngine    — PO canonical vs GO canonical → report rows + alerts
  5. ReportWriter     — Compare_Report.xlsx + Alerts.json

No hardcoded sheet names, row/column indices, customer names, or style patterns.
"""
