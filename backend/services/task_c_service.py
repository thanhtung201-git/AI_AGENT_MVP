"""
task_c_service.py — Task C: Verify Trimlist

Flow:
  1. Đọc Trimlist Excel hiện có  → structured text
  2. Đọc Tech Pack (optional)    → source document
  3. Đọc Trim Master (optional)  → reference rules
  4. LLM verify từng dòng        → verification report
"""
import os
import logging
from typing import Any, Dict, List, Optional

from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_VERIFY_PROMPT = """
You are a garment QA specialist verifying a trim list against source documents.

TRIMLIST TO VERIFY:
{trimlist_content}

SOURCE DOCUMENTS:
{source_content}

For each row in the trimlist, verify:
1. Is the description/spec consistent with what's in the source documents?
2. Is the supplier/brand correct per Trim Master rules?
3. Is the quantity per garment reasonable?

Also check: are there any items in the source documents that are MISSING from the trimlist?

OUTPUT — valid JSON only:
{{
  "verified_lines": [
    {{
      "row": 1,
      "item_no": "1",
      "description": "Main Label",
      "status": "ok",
      "issue": "",
      "source_ref": "Tech Pack page 3",
      "severity": "ok"
    }}
  ],
  "missing_items": [
    "Care Label — found in Tech Pack but not in trimlist"
  ],
  "summary": "15 items verified: 12 OK, 2 mismatches, 1 missing",
  "ok_count": 12,
  "mismatch_count": 2,
  "missing_count": 1,
  "unverified_count": 0
}}

status values: "ok" | "mismatch" | "missing" | "unverified"
severity values: "ok" | "warning" | "critical"

If source documents are empty, mark all lines as "unverified" and note that sources are missing.
"""


class TaskCService:
    """Verify trimlist against source documents using LLM."""

    def __init__(self):
        self.llm = GroqClient()

    def run(
        self,
        trimlist_path: str,
        techpack_path: Optional[str] = None,
        master_trim_path: Optional[str] = None,
        garment_type: str = "Men Woven",
    ) -> Dict[str, Any]:
        """
        Returns:
        {
          "success": bool,
          "verified_lines": [...],
          "missing_items": [...],
          "summary": str,
          "stats": {...},
          "error": str | None,
        }
        """
        # ── Đọc Trimlist ────────────────────────────────────────────────────────
        try:
            trimlist_text = self._read_trimlist(trimlist_path)
        except Exception as e:
            return {"success": False, "error": f"Lỗi đọc Trimlist: {e}"}

        # ── Đọc sources (optional) ──────────────────────────────────────────────
        source_parts = []

        if techpack_path and os.path.exists(techpack_path):
            try:
                tp_text = self._read_source(techpack_path)
                if tp_text:
                    source_parts.append(f"=== TECH PACK ===\n{tp_text[:4000]}")
            except Exception as e:
                logger.warning(f"TaskC: đọc Tech Pack lỗi — {e}")

        if master_trim_path and os.path.exists(master_trim_path):
            try:
                mt_text = self._read_master_trim(master_trim_path, garment_type)
                if mt_text:
                    source_parts.append(f"=== TRIM MASTER ({garment_type}) ===\n{mt_text[:3000]}")
            except Exception as e:
                logger.warning(f"TaskC: đọc Trim Master lỗi — {e}")

        source_content = "\n\n".join(source_parts) if source_parts else "(no source documents provided)"

        # ── LLM Verify ──────────────────────────────────────────────────────────
        try:
            report = self._verify_with_llm(trimlist_text, source_content)
        except Exception as e:
            return {"success": False, "error": f"LLM verify thất bại: {e}"}

        verified_lines = report.get("verified_lines") or []
        missing_items  = report.get("missing_items") or []

        return {
            "success":        True,
            "verified_lines": verified_lines,
            "missing_items":  missing_items,
            "summary":        report.get("summary") or f"{len(verified_lines)} dòng đã kiểm tra",
            "stats": {
                "ok_count":         report.get("ok_count", 0),
                "mismatch_count":   report.get("mismatch_count", 0),
                "missing_count":    report.get("missing_count", len(missing_items)),
                "unverified_count": report.get("unverified_count", 0),
                "total":            len(verified_lines),
            },
            "error": None,
        }

    # ── Private helpers ─────────────────────────────────────────────────────────

    def _read_trimlist(self, path: str) -> str:
        from tools.reader import read_file
        result = read_file(path)
        if not result.get("success"):
            raise RuntimeError(result.get("error", "read_file thất bại"))
        return result["text"][:8000]

    def _read_source(self, path: str) -> str:
        from tools.reader import read_file
        result = read_file(path)
        if not result.get("success"):
            return ""
        return result.get("text") or ""

    def _read_master_trim(self, path: str, garment_type: str) -> str:
        from backend.extractors.master_trim_reader import MasterTrimReader
        reader = MasterTrimReader(path)
        result = reader.read(garment_type)
        if not result.get("success"):
            return ""
        items = result.get("items") or []
        lines = []
        for it in items:
            parts = []
            for k in ("trim_item", "spec", "supplier", "supplier_code", "qty_per_garment"):
                v = it.get(k)
                if v:
                    parts.append(f"{k}={v}")
            lines.append(" | ".join(parts))
        return "\n".join(lines[:150])

    def _verify_with_llm(self, trimlist_text: str, source_content: str) -> Dict:
        prompt = _VERIFY_PROMPT.format(
            trimlist_content=trimlist_text,
            source_content=source_content,
        )
        result = self.llm.extract_json_with_retry(
            system_prompt="You are a garment QA specialist. Return valid JSON only.",
            user_content=prompt,
            max_retries=1,
        )
        return result if isinstance(result, dict) else {}
