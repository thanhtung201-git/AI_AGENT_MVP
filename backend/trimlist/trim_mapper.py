"""
trim_mapper.py — Step 2: Map Tech Pack items to Trim Master.

The LLM receives:
  - All extracted trim items (from Tech Pack)
  - Full Trim Master content (structured rows)

LLM performs SEMANTIC matching:
  "Chest Fusing" → Trim Master row with code FT770ES, supplier, spec, placement.

NO hardcoded mappings. All data comes from the actual Trim Master file.
"""
import json
import logging
from typing import Dict, List, Optional

from backend.trimlist.traceability import TrimRow, TrimSource
from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_SYSTEM = """You are a garment trim specialist matching materials to a Trim Master database.
Return valid JSON only. No markdown, no explanation."""

_PROMPT = """
You are mapping garment trim items to a Trim Master database.

TASK:
For each item in TRIM ITEMS TO MAP, find the best matching row in the TRIM MASTER DATA.
Use semantic/conceptual matching — not just exact string match.
Example: "Chest fusing" → match Trim Master rows about "Fusing", "Interlining".
Example: "Sewing Thread" → match rows about "Thread", "Poly Thread".

INSTRUCTIONS:
1. Search the Trim Master for the closest match by material type and usage.
2. If a match is found, extract ALL available fields from that row.
3. "material_code" in the Trim Master = the buyer's material code (e.g. FT770ES, DK320, HL2025-xxx).
   This is the EXACT code to return as matched_code.
4. "std_consumption" in the Trim Master = standard consumption (e.g. "1.35 M", "2 PCS").
   Return this as matched_consumption.
5. If NO match is found, return null for all fields. DO NOT guess or invent codes.
6. Confidence: "high" = same material type + usage, "medium" = similar type, "low" = possible match.
7. Confidence "none" = no reasonable match found.

TRIM ITEMS TO MAP:
{trim_items}

TRIM MASTER DATA:
{trim_master}

RETURN JSON:
{{
  "mappings": [
    {{
      "input_material_name": "Chest Fusing",
      "matched_code":        "FT770ES",
      "matched_supplier":    "Freudenberg Korea",
      "matched_spec":        "FT770ES woven fusible, 75g/m2, polyester",
      "matched_placement":   "Front chest, collar stand, cuff",
      "matched_remark":      "Pre-shrunk before cutting",
      "matched_consumption": "0.15 M",
      "master_ref":          "Men Woven Row 8 — FT770ES Fusing",
      "confidence":          "high"
    }},
    {{
      "input_material_name": "Custom Embroidery Patch",
      "matched_code":        null,
      "matched_supplier":    null,
      "matched_spec":        null,
      "matched_placement":   null,
      "matched_remark":      null,
      "matched_consumption": null,
      "master_ref":          null,
      "confidence":          "none"
    }}
  ]
}}

IMPORTANT:
- Every item in TRIM ITEMS TO MAP MUST have an entry in mappings (even if confidence=none).
- matched_code MUST come from the 'material_code' column of Trim Master. Never invent it.
- matched_supplier MUST come from the 'supplier' column of Trim Master. Never invent it.
- If master_ref is null, the item will be flagged as missing_code in validation.
"""


class TrimMasterMapper:
    """
    Maps extracted Tech Pack items to Trim Master using LLM semantic matching.
    Enriches TrimRow objects with material_code, supplier, spec, placement, remark.
    """

    def __init__(self):
        self.llm = GroqClient()

    def map(
        self,
        rows: List[TrimRow],
        master_items: List[Dict],
        sheet_name: str = "",
    ) -> List[TrimRow]:
        """
        Enrich rows with data from Trim Master.

        Args:
            rows:         List[TrimRow] from TechPackExtractor
            master_items: List[Dict] from MasterTrimReader (the raw rows)
            sheet_name:   Trim Master sheet used (for traceability)

        Returns:
            Same rows, with material_code/supplier/spec enriched where found.
        """
        if not rows:
            return rows
        if not master_items:
            logger.warning("TrimMasterMapper: no Trim Master data — skipping mapping")
            return rows

        master_text = self._format_master(master_items, sheet_name)
        items_text  = self._format_items(rows)

        mappings = self._call_llm(items_text, master_text)
        if not mappings:
            logger.warning("TrimMasterMapper: LLM returned empty mappings")
            return rows

        mapping_index = self._index_mappings(mappings)
        self._apply_mappings(rows, mapping_index, sheet_name)

        matched = sum(1 for r in rows if r.material_code or r.supplier)
        logger.info(f"TrimMasterMapper: {matched}/{len(rows)} items mapped to Trim Master")
        return rows

    def _format_master(self, items: List[Dict], sheet_name: str) -> str:
        """Convert Trim Master items to numbered text for LLM.

        Note: master item key 'supplier_code' is the MATERIAL CODE (e.g. FT770ES),
        not the vendor's article number. We expose it as 'material_code' so the LLM
        maps it correctly to 'matched_code' in the response.
        """
        lines = [f"Sheet: {sheet_name}"]
        for i, it in enumerate(items, 1):
            parts = [f"Row {i}"]
            # trim_item = the material/trim description in the master
            if it.get("trim_item"):
                parts.append(f"item={it['trim_item']}")
            # supplier_code in master is actually the MATERIAL CODE (e.g. FT770ES, DK320)
            if it.get("supplier_code"):
                parts.append(f"material_code={it['supplier_code']}")
            if it.get("supplier"):
                parts.append(f"supplier={it['supplier']}")
            if it.get("qty_per_garment"):
                qty = it["qty_per_garment"]
                unit = it.get("unit", "")
                parts.append(f"std_consumption={qty} {unit}".strip())
            if it.get("remark"):
                parts.append(f"remark={it['remark']}")
            lines.append(" | ".join(parts))
        return "\n".join(lines[:300])  # cap at 300 rows to stay in token budget

    def _format_items(self, rows: List[TrimRow]) -> str:
        """Format TrimRow list for LLM input."""
        result = []
        for i, row in enumerate(rows, 1):
            parts = [f"{i}. {row.material_name}"]
            if row.category:    parts.append(f"category={row.category}")
            if row.spec:        parts.append(f"spec={row.spec}")
            if row.placement:   parts.append(f"placement={row.placement}")
            result.append(" | ".join(parts))
        return "\n".join(result)

    def _call_llm(self, items_text: str, master_text: str) -> list:
        try:
            prompt = _PROMPT.format(
                trim_items=items_text,
                trim_master=master_text,
            )
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=1,
            )
            return result.get("mappings") or []
        except Exception as e:
            logger.error(f"TrimMasterMapper LLM error: {e}")
            return []

    def _index_mappings(self, mappings: list) -> Dict[str, Dict]:
        """Index mappings by input_material_name (lowercase) for fast lookup."""
        index = {}
        for m in mappings:
            name = (m.get("input_material_name") or "").lower().strip()
            if name:
                index[name] = m
        return index

    def _apply_mappings(
        self,
        rows: List[TrimRow],
        mapping_index: Dict[str, Dict],
        sheet_name: str,
    ) -> None:
        """Apply LLM mappings to TrimRow objects in-place."""
        for row in rows:
            key = row.material_name.lower().strip()
            m   = mapping_index.get(key)
            if not m:
                continue
            confidence = m.get("confidence") or "none"
            if confidence == "none":
                continue

            # Tech Pack values take priority over Trim Master (only fill empty fields)
            if not row.material_code and m.get("matched_code"):
                row.material_code = m["matched_code"]
            if not row.supplier and m.get("matched_supplier"):
                row.supplier = m["matched_supplier"]
            if not row.spec and m.get("matched_spec"):
                row.spec = m["matched_spec"]
            if not row.placement and m.get("matched_placement"):
                row.placement = m["matched_placement"]
            if not row.remark and m.get("matched_remark"):
                row.remark = m["matched_remark"]
            # Fill consumption from master standard if tech pack didn't provide one
            if not row.consumption and m.get("matched_consumption"):
                row.consumption = m["matched_consumption"]
                row.source.master_ref = (row.source.master_ref or "") + " [std_consumption]"

            # Flag low-confidence matches so validator can alert
            if confidence == "low":
                row.alerts.append(
                    f"WARNING: Trim Master match low confidence — verify '{row.material_code or '?'}'"
                )

            if m.get("master_ref"):
                row.source.master_ref = f"{sheet_name} — {m['master_ref']}"
