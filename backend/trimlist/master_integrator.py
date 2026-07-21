"""
master_integrator.py — Phase 3: Intelligent Trim Master Integration

Replaces trim_mapper.py.

Key differences from the old mapper:
1. LLM decides the merge — not Python priority rules
2. Conflicts are detected and reported (not silently overwritten)
3. Tech Pack is always preferred; Trim Master fills gaps and adds codes
4. Works for any Trim Master structure (any columns, any sheet names)
5. Per-field traceability on every merged value

The Trim Master is treated as a REFERENCE DATABASE, not an override.
"""
import logging
from typing import Any, Dict, List, Optional

from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

# ── LLM Prompts ───────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a garment merchandising specialist merging material data from "
    "a Tech Pack and a Trim Master database. Return valid JSON only. No markdown."
)

_MERGE_PROMPT = """
You are merging garment material data from two sources:
  SOURCE A: Tech Pack (primary — extracted directly from the design document)
  SOURCE B: Trim Master (reference database — standard codes and suppliers)

MERGING RULES:
1. Tech Pack values ALWAYS take priority over Trim Master
2. If Tech Pack has a field → keep it, even if Trim Master disagrees
3. If Tech Pack field is empty/null → fill from Trim Master
4. If both sources have DIFFERENT values for the same non-empty field → CONFLICT:
   - Keep the Tech Pack value
   - Record the conflict in "conflicts" list (state BOTH values, e.g.
     "material_code: Tech Pack '8960' vs Trim Master '7712'")
   - Do NOT silently overwrite
5. Match is SEMANTIC — "Chest Fusing" matches "Fusible Interlining" in Trim Master
6. Report confidence: "high" | "medium" | "low" | "none"
   - "none" → no reasonable match found in Trim Master

CRITICAL — PRECISE MATCHING (avoid wrong / blanket codes):
7. A Trim Master code/supplier belongs to exactly ONE material. NEVER put the SAME
   Trim Master code on two different materials. If two Tech Pack items seem to point
   at the same Master row, keep the code only on the single best match and leave the
   other's material_code null.
8. Only borrow a code/supplier from Trim Master when it is the SAME material (same
   category AND same function) — not merely a similar-sounding name. A "Butterfly"
   pin is NOT a "Polybag"; a "Collar band" is NOT a "Care label".
9. When unsure, DO NOT GUESS: set confidence "none", leave material_code null. A
   missing code the user fills in is far safer than a wrong code.
10. Do NOT pull in Trim Master rows that no Tech Pack material matches — this step
    only ENRICHES the Tech Pack items given below, it never adds new items.

TECH PACK MATERIALS:
{tech_pack_items}

TRIM MASTER DATABASE:
{trim_master_items}

For EACH Tech Pack material, find the best Trim Master match (if any) and produce
a merged record.

Return JSON:
{{
  "merged_materials": [
    {{
      "material_name":  "Care Label",
      "material_code":  "111086874X",
      "supplier":       "EAP",
      "supplier_code":  null,
      "category":       "LABEL",
      "spec":           "26SS NEW CARE LABEL, Side Seam",
      "placement":      "Side Seam",
      "color":          null,
      "colorways":      null,
      "consumption":    "1 PCS",
      "unit":           "PCS",
      "remark":         null,
      "sources": {{
        "material_code":  "Trim Master — Men Woven Row 4",
        "supplier":       "Trim Master — Men Woven Row 4",
        "consumption":    "Tech Pack — BOM Table Row 12"
      }},
      "conflicts":      [],
      "master_match":   "Care Label (Shirt)",
      "confidence":     "high"
    }},
    {{
      "material_name":  "Body Fabric",
      "material_code":  null,
      "supplier":       "TESSELLATION",
      "supplier_code":  null,
      "category":       "FABRIC/YARN",
      "spec":           "100% Cotton Twill 70X80",
      "placement":      "Body",
      "color":          null,
      "colorways":      {{"N2": "HL2025-39751N", "W2": "HL2025-39748N"}},
      "consumption":    null,
      "unit":           "M",
      "remark":         null,
      "sources": {{
        "supplier":   "Tech Pack — Fabric Specification Table",
        "colorways":  "Tech Pack — Colorway Table"
      }},
      "conflicts":      [],
      "master_match":   null,
      "confidence":     "none"
    }}
  ]
}}

IMPORTANT:
- Every Tech Pack material MUST appear in merged_materials (even if confidence=none)
- Sources object must cite where each non-null field value came from
- "master_match" = the Trim Master item name that was matched (or null if no match)
- Never invent codes or suppliers — only use what is explicitly in the data
"""


class MasterIntegrator:
    """
    Phase 3: Merges Tech Pack materials with Trim Master using LLM reasoning.

    Input : List[Dict] from MaterialExtractor + List[Dict] from MasterTrimReader
    Output: List[Dict] — merged canonical materials with conflict tracking
    """

    def __init__(self):
        self.llm = GroqClient()

    def merge(
        self,
        tech_pack_items: List[Dict],
        master_items: List[Dict],
        sheet_name: str = "",
    ) -> List[Dict]:
        """
        Merge Tech Pack materials with Trim Master.

        Args:
            tech_pack_items : output of MaterialExtractor.extract()
            master_items    : output of MasterTrimReader.read()["items"]
            sheet_name      : for traceability (which sheet was used)

        Returns:
            List[Dict] — merged materials, each with "sources" and "conflicts"
        """
        if not tech_pack_items:
            return []

        if not master_items:
            logger.info("MasterIntegrator: no Trim Master data — returning Tech Pack items unchanged")
            return [self._add_empty_sources(item) for item in tech_pack_items]

        # Process in batches to stay within token limits
        # Smaller batch = LLM returns all items, fewer drops
        batch_size = 12
        merged_all: List[Dict] = []

        for i in range(0, len(tech_pack_items), batch_size):
            batch = tech_pack_items[i: i + batch_size]
            merged_batch = self._llm_merge(batch, master_items, sheet_name)
            merged_all.extend(merged_batch)

        # Fallback: if LLM returned fewer items than input, add missing ones
        merged_all = self._ensure_all_items_present(tech_pack_items, merged_all)

        matched = sum(1 for m in merged_all if m.get("confidence") not in (None, "none"))
        conflicts = sum(1 for m in merged_all if m.get("conflicts"))
        logger.info(
            f"MasterIntegrator: {matched}/{len(merged_all)} matched, "
            f"{conflicts} conflict(s)"
        )
        return merged_all

    # ── Private helpers ───────────────────────────────────────────────────────

    def _llm_merge(
        self,
        tp_items: List[Dict],
        master_items: List[Dict],
        sheet_name: str,
    ) -> List[Dict]:
        tp_text     = self._format_tp_items(tp_items)
        master_text = self._format_master_items(master_items, sheet_name)

        try:
            prompt = _MERGE_PROMPT.format(
                tech_pack_items=tp_text,
                trim_master_items=master_text,
            )
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=2,
            )
            merged = result.get("merged_materials") or []
            return [m for m in merged if isinstance(m, dict) and m.get("material_name")]
        except Exception as e:
            logger.error(f"MasterIntegrator LLM error: {e}")
            # Return Tech Pack items with empty sources as fallback
            return [self._add_empty_sources(item) for item in tp_items]

    def _format_tp_items(self, items: List[Dict]) -> str:
        """Format Tech Pack items for LLM prompt."""
        lines = []
        for i, item in enumerate(items, 1):
            parts = [f"Item {i}: {item.get('material_name', '?')}"]
            for field in ("category", "spec", "placement", "color", "colorways",
                          "consumption", "unit", "remark", "material_code",
                          "supplier", "supplier_code"):
                val = item.get(field)
                if val:
                    parts.append(f"  {field}: {val}")
            # Include enrichment source hints
            for k, v in item.items():
                if k.startswith("_source_") and v:
                    parts.append(f"  {k}: {v}")
            lines.append("\n".join(parts))
        return "\n\n".join(lines)

    def _format_master_items(self, items: List[Dict], sheet_name: str) -> str:
        """Format Trim Master items for LLM prompt — capped at 300 rows."""
        lines = [f"Sheet: {sheet_name}" if sheet_name else "Trim Master:"]
        for i, item in enumerate(items[:300], 1):
            parts = [f"Row {i}: {item.get('trim_item', '?')}"]
            code = item.get("supplier_code") or ""
            if code:
                parts.append(f"  material_code: {code[:60]}")
            if item.get("supplier"):
                parts.append(f"  supplier: {item['supplier']}")
            if item.get("qty_per_garment"):
                qty  = item["qty_per_garment"]
                unit = item.get("unit", "")
                parts.append(f"  std_consumption: {qty} {unit}".strip())
            if item.get("remark"):
                parts.append(f"  remark: {item['remark'][:100]}")
            lines.append("\n".join(parts))
        return "\n\n".join(lines)

    def _add_empty_sources(self, item: Dict) -> Dict:
        """Add empty sources/conflicts to a Tech Pack item (used in fallback)."""
        merged = dict(item)
        merged.setdefault("sources", {})
        merged.setdefault("conflicts", [])
        merged.setdefault("master_match", None)
        merged.setdefault("confidence", "none")
        return merged

    def _ensure_all_items_present(
        self, original: List[Dict], merged: List[Dict]
    ) -> List[Dict]:
        """
        If the LLM dropped some items (output fewer than input),
        add the missing original items with empty sources.
        Uses fuzzy name matching to avoid re-adding renamed items.
        """
        def _norm(s: str) -> str:
            import re
            return re.sub(r"[^a-z0-9]", "", (s or "").lower())

        merged_keys = {_norm(m.get("material_name") or "") for m in merged}

        # Also track by material_code to catch renames
        merged_codes = {
            (m.get("material_code") or "").strip().lower()
            for m in merged
            if m.get("material_code")
        }

        result = list(merged)
        for orig in original:
            orig_key  = _norm(orig.get("material_name") or "")
            orig_code = (orig.get("material_code") or "").strip().lower()

            # Check if present by name (normalized) or code
            name_present = orig_key in merged_keys
            code_present = orig_code and orig_code in merged_codes

            if not name_present and not code_present:
                logger.warning(
                    f"MasterIntegrator: LLM dropped '{orig.get('material_name')}' — "
                    f"re-adding from Tech Pack"
                )
                result.append(self._add_empty_sources(orig))
        return result
