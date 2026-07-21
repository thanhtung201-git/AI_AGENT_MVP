"""
task_b_service.py — Task B entry point.

Delegates to the new modular pipeline:
  backend/trimlist/pipeline.py → TrimlistPipeline

This file stays thin — it only handles path resolution and meta assembly.
"""
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TaskBService:
    """Task B: Tech Pack + Trim Master + Email → Trimlist via modular pipeline."""

    def run(
        self,
        techpack_path: str,
        master_trim_path: Optional[str] = None,
        email_note: str = "",
        garment_type: str = "",
        buyer_code: str = "",
        branch: str = "",
        branch_confirmed: bool = False,
        meta: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        from backend.trimlist.pipeline import TrimlistPipeline
        return TrimlistPipeline().run(
            techpack_path=techpack_path,
            master_trim_path=master_trim_path,
            email_note=email_note,
            buyer_code=buyer_code,
            garment_type=garment_type,
            branch=branch,
            branch_confirmed=branch_confirmed,
            meta=meta or {},
        )
