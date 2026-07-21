"""
extractor.py — Step 1: Extract ALL trim items from Tech Pack using LLM.

Goal:
  Read Tech Pack PDF/Excel and extract EVERY material/trim mentioned,
  including fabrics, interlining, labels, buttons, thread, zippers, packing.

Key output per item:
  - category (classified)
  - material_name (exact text from Tech Pack)
  - spec (specifications stated in Tech Pack)
  - placement (where it goes, if stated)
  - color (color code or instruction like DTM)
  - consumption (qty per garment, if stated)
  - source_ref (section / page / row reference)

The LLM must cite WHERE it found each item (source_ref).
This is used for traceability in Task C.
"""
import json
import logging
from typing import List, Optional

from backend.trimlist.traceability import TrimRow, TrimSource, classify_category, CATEGORY_ORDER
from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_SYSTEM = """You are a garment Tech Pack analyst.
Extract ALL trim/material items from the Tech Pack text.
Return valid JSON only. No markdown, no explanation."""

_PROMPT = """
Analyze this Tech Pack and extract EVERY material or trim item mentioned.

EXTRACT ALL OF THE FOLLOWING (if present):
- Main fabric / shell fabric / body fabric / lining fabric
- Interlining / Fusing / Interfacing / Chest canvas / Collar canvas
- Sewing thread (all types)
- Buttons (every type: main, inner, decorative, shank, flat)
- Zippers (main zip, pocket zip, fly zip, separating zip)
- Labels: Main label, Size label, Care/Content label, Country of origin label
- Hangtag / Price tag / RFID tag / Barcode sticker / Point label
- Elastic / Drawcord / Cord stopper / Aglet
- Ribbon / Tape / Braid / Binding / Piping
- Hook & Eye / Snap button / Velcro
- Polybag / Inner bag / Ziplock bag
- Tissue paper / Collar stiffener / Butterfly board / Cardboard insert
- Carton / Carton tape / Desiccant / Silica gel
- Any other accessory or material mentioned

For EACH item, extract these EIGHT fields:

1. "category": exactly one of [FABRIC/YARN, INTERLINING, THREAD & BUTTON, LABEL, PACKING, OTHER]

2. "material_name": the EXACT name used in the Tech Pack
   Examples: "Chest Fusing", "Main Brand Label", "YKK Zipper", "Sewing Thread"

3. "spec": technical specifications ONLY — weight, composition, size, finish
   Examples: "Non-woven fusible, 90g/m2", "Woven label, 30x50mm", "100% Poly #120"
   DO NOT include color codes here.

4. "placement": SPECIFIC location on the garment — use exact text from Tech Pack
   Be as specific as possible:
   Good: "Collar Upper Layer", "CF Placket Inner", "Left Side Seam", "CB Neck Seam"
   Bad:  "Collar", "Body", "Front"
   If multiple placements, list them: "Collar / Cuff / Front Placket"

5. "color": color instruction ONLY — do NOT put this in consumption
   Examples: "DTM", "N2", "W2", "Black", "White", "Navy", "To Match Fabric"
   Korean 2-letter codes (N2, W2, BK, WH, GY) are color codes — put them HERE, not in consumption.
   If no color stated, return null.

6. "consumption": NUMERIC QUANTITY ONLY — format: "<number> <unit>"
   Examples: "1.35 M", "2 PCS", "0.25 YDS", "300 M", "1 CONE"
   STRICT RULES for consumption:
   - NEVER put color codes (N2, W2, DTM) here — those go in "color"
   - NEVER put placement or spec here
   - Only number + unit: "1 M", "2 PCS", "0.5 YDS"
   - If not stated, return null

7. "unit": unit of measure matching the consumption
   By category:
   - FABRIC/YARN → "M" or "YDS" or "KG"
   - INTERLINING  → "M"
   - Thread       → "M" or "CONE"
   - Button/Zipper/Label/Packing → "PCS"
   If not stated, infer from category.

8. "source_ref": WHERE you found this — page, section, table, row
   Examples: "Section 16 BOM Table Row 3", "Trim Spec Page 2 Row 5", "Cover Page"
   THIS FIELD IS REQUIRED. Never leave it null.

9. "colorways": ONLY when the tech pack specifies DIFFERENT colors for different colorways/lots.
   Format: {{"N2": "Navy DTM", "W2": "White", "BK": "Black"}}
   - Use this INSTEAD OF "color" when colors differ per colorway
   - If all colorways share the same color instruction, use "color" field only
   - If only one colorway or no colorway distinction, return null

10. "bom_row_number": the sequential row number of this item in the BOM table (1, 2, 3...).
    Used to count and verify total BOM lines. Required for every item.

IMPORTANT RULES:
- Include EVERY item, even if specification is incomplete
- NEVER invent data — if a field is not stated, return null (except source_ref and unit)
- NEVER put color codes into consumption — N2, W2 etc. are colors, not quantities
- NEVER put spec or placement into consumption
- If the same item appears with multiple placements, create ONE row per placement

OUTPUT FORMAT (JSON only):
{{
  "bom_total_lines": 12,
  "items": [
    {{
      "bom_row_number": 1,
      "category": "INTERLINING",
      "material_name": "Chest Fusing",
      "spec": "Non-woven fusible interlining, 90g/m2",
      "placement": "Front Chest Panel / Collar Stand",
      "color": "White",
      "colorways": null,
      "consumption": "0.15 M",
      "unit": "M",
      "source_ref": "Section 16 BOM Table Row 5"
    }},
    {{
      "bom_row_number": 2,
      "category": "LABEL",
      "material_name": "Main Brand Label",
      "spec": "Woven label, 30mm x 50mm",
      "placement": "Center Back Neck Seam",
      "color": null,
      "colorways": null,
      "consumption": "1 PCS",
      "unit": "PCS",
      "source_ref": "Trim Spec Page 3 Table Row 1"
    }},
    {{
      "bom_row_number": 3,
      "category": "THREAD & BUTTON",
      "material_name": "Sewing Thread",
      "spec": "100% Polyester, 120/2",
      "placement": "All Seams",
      "color": null,
      "colorways": {{"N2": "Navy DTM", "W2": "White DTM"}},
      "consumption": "300 M",
      "unit": "M",
      "source_ref": "BOM Row 8"
    }}
  ]
}}

TECH PACK CONTENT:
{content}
"""


class TechPackExtractor:
    """
    Extracts all trim items from a Tech Pack document using LLM.
    Returns a list of TrimRow objects with source traceability.
    """

    def __init__(self):
        self.llm = GroqClient()

    def extract(self, raw_text: str) -> tuple:
        """
        Main entry: extract all trim items from raw Tech Pack text.

        Returns:
            (List[TrimRow], bom_line_count: int)
            bom_line_count = total BOM rows reported by LLM (for self-check comparison)
        """
        if not raw_text or not raw_text.strip():
            logger.warning("TechPackExtractor: empty text")
            return [], 0

        chunks = self._split_into_chunks(raw_text, max_chars=9000)
        bom_chunks = [c for c in chunks if self._is_bom_chunk(c)]
        if not bom_chunks:
            bom_chunks = chunks  # fallback: use all
            logger.info("TechPackExtractor: no BOM section detected, using all chunks")
        else:
            logger.info(f"TechPackExtractor: {len(bom_chunks)}/{len(chunks)} BOM chunks")

        raw_items: list = []
        bom_total_lines: int = 0
        for chunk in bom_chunks:
            result_dict, items = self._call_llm_full(chunk)
            raw_items.extend(items)
            bom_total_lines += result_dict.get("bom_total_lines") or 0

        rows = self._to_trim_rows(raw_items)
        rows = self._deduplicate(rows)
        logger.info(
            f"TechPackExtractor: extracted {len(rows)} trim items "
            f"(BOM total reported: {bom_total_lines}) from {len(bom_chunks)} chunk(s)"
        )
        return rows, bom_total_lines

    def _call_llm_full(self, chunk: str) -> tuple:
        """Returns (result_dict, items_list)."""
        try:
            prompt = _PROMPT.format(content=chunk)
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=2,
            )
            if isinstance(result, list):
                return {}, [it for it in result if isinstance(it, dict)]
            elif isinstance(result, dict):
                items = result.get("items") or result.get("trim_items") or []
                return result, [it for it in items if isinstance(it, dict)]
            else:
                logger.warning(f"TechPackExtractor: unexpected LLM result type {type(result).__name__}, skipping")
                return {}, []
        except Exception as e:
            logger.warning(f"TechPackExtractor LLM error (chunk skipped): {e}")
            return {}, []

    def _to_trim_rows(self, raw_items: list) -> List[TrimRow]:
        rows = []
        for item in raw_items:
            name = str(item.get("material_name") or "").strip()
            if not name:
                continue

            category = item.get("category") or classify_category(name)
            if category not in CATEGORY_ORDER:
                category = classify_category(name)

            # Infer unit: prefer LLM-extracted, else default "pcs" (normalizer will fix)
            unit_raw = (item.get("unit") or "").strip().upper()
            unit = unit_raw if unit_raw else "pcs"

            # Handle colorways dict (multi-colorway) vs single color
            colorways_raw = item.get("colorways") or {}
            color_val = item.get("color") or None
            if colorways_raw and isinstance(colorways_raw, dict):
                # Multi-colorway: store in colors dict, clear single color
                colors = {k.upper(): v for k, v in colorways_raw.items() if k and v}
                color_val = None  # color field unused when colorways set
            else:
                colors = {}

            row = TrimRow(
                category=category,
                sort_key=CATEGORY_ORDER.get(category, 99),
                material_name=name,
                spec=item.get("spec") or None,
                placement=item.get("placement") or None,
                color=color_val,
                colors=colors,
                consumption=item.get("consumption") or None,
                unit=unit,
                source=TrimSource(
                    techpack_ref=item.get("source_ref") or "Tech Pack",
                ),
            )
            rows.append(row)
        return rows

    def _deduplicate(self, rows: List[TrimRow]) -> List[TrimRow]:
        """Remove duplicates: same material_name + placement → keep one."""
        seen: set = set()
        unique = []
        for row in rows:
            key = (row.material_name.lower().strip(), (row.placement or "").lower().strip())
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique

    @staticmethod
    def _is_bom_chunk(text: str) -> bool:
        import re
        t = text.lower()
        # Direct BOM indicators
        if re.search(r"expected\s+trim\s+list|trim\s+specification|bill\s+of\s+material", t):
            return True
        # Has table-like structure with trim keywords
        keywords = ["supplier", "placement", "trim", "label", "fusing", "thread", "button"]
        hits = sum(1 for k in keywords if k in t)
        return hits >= 3

    @staticmethod
    def _split_into_chunks(text: str, max_chars: int = 9000) -> List[str]:
        if len(text) <= max_chars:
            return [text]
        chunks, current = [], ""
        for line in text.splitlines(keepends=True):
            if len(current) + len(line) > max_chars:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)
        return chunks
