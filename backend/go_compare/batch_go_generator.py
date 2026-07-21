"""
batch_go_generator.py — Deterministic Python: CanonicalOrder → Batch_GO_Output.xlsx.

No LLM here. Excel writing must be deterministic and reproducible.

The output MUST match the company's fixed-schema ERP import file, so we do NOT
build a workbook from scratch. Instead we open the real `Batch GO Upload` template
(see settings.BATCH_GO_TEMPLATE), keep every sheet / section / header / format,
delete only the sample data rows, write our PO's values into the right cells, and
validate the result against the template before returning it. All of that lives in
template_writer.py; this module is the thin, stable entry point the pipeline calls.
"""
from __future__ import annotations

import logging

from backend.config.settings import settings
from backend.go_compare.canonical import CanonicalOrder
from backend.go_compare.template_writer import TemplateBatchGOWriter, validate_structure

logger = logging.getLogger(__name__)


class BatchGOGenerator:
    """Fills the real Batch GO Upload template from a canonical order."""

    def __init__(self, template_path: str | None = None):
        self.template_path = template_path or settings.BATCH_GO_TEMPLATE

    def generate(self, order: CanonicalOrder, output_path: str) -> str:
        TemplateBatchGOWriter(self.template_path).write(order, output_path)

        # Fixed-schema guard: never hand back a file the ERP import would reject.
        errors = validate_structure(self.template_path, output_path)
        if errors:
            detail = "; ".join(errors)
            logger.error(f"BatchGOGenerator: output không khớp template — {detail}")
            raise ValueError(f"File Batch GO không khớp cấu trúc template: {detail}")

        logger.info(f"BatchGOGenerator: saved {output_path} (khớp template)")
        return output_path
