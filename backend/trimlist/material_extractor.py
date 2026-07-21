"""
material_extractor.py — Phase 2: Material Extraction with Document-Wide Reasoning

Two-pass extraction:
  Pass A — Extract all materials from identified BOM sections
  Pass B — Cross-reference full document to enrich materials with missing fields

Zero hardcoded page numbers, column indices, company names, or document layouts.
Works for any Tech Pack from any brand.

Every extracted value carries a source citation (which section/table it came from).
"""
import logging
from typing import Any, Dict, List, Optional

from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

# ── LLM Prompts ───────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a garment trim extraction specialist. "
    "Return valid JSON only. No markdown, no explanation."
)

_EXTRACT_PROMPT = """
Extract EVERY material and trim item from the BOM/material section below.

For EACH item, extract ALL fields that exist in this section.
Do NOT invent data — only extract what is explicitly written.
If a field is not present, return null.

FIELDS TO EXTRACT per item:
1.  "material_name"   : exact name as written in the document
2.  "material_code"   : internal code / item code / article number / reference number
                        (e.g. "FT770ES", "220019916X", "111086874X", "YKK-561")
                        Look in ANY column that has codes, numbers, or article references
3.  "supplier"        : supplier / vendor / brand / manufacturer name
4.  "supplier_code"   : vendor's own article code (different from buyer's material code)
5.  "category"        : classify as one of:
                        FABRIC/YARN | INTERLINING | THREAD & BUTTON | LABEL | PACKING | OTHER
6.  "spec"            : technical specification — weight, composition, size, finish, weave
                        Do NOT include color codes or placement here
7.  "placement"       : specific location on the garment (e.g. "Center Back Neck", "CF Placket")
8.  "color"           : color instruction ONLY — must be a COLOR, not a spec
                        Valid: "DTM", "White", "Navy", "N2", "W2", "To Match"
                        Invalid: any text that is a spec, weight, composition, or code
                        If color is not explicitly stated, return null
9.  "colorways"       : object when DIFFERENT colors exist per colorway
                        e.g. {{"N2": "Navy DTM", "W2": "White"}}
                        Use this INSTEAD of "color" when the document shows color varies by colorway
                        Colorway keys are typically 2-letter codes (N2, W2, BK) or color names
10. "consumption"     : quantity per garment — MUST be a NUMBER + UNIT only
                        Valid: "1.35 M", "2 PCS", "300 M", "1 CONE"
                        Invalid: fabric weave counts ("160X136"), weights ("90g"), spec text
                        If no clear quantity-per-garment is stated, return null
11. "unit"            : unit of measure (M / YDS / PCS / CONE / KG / SET)
                        Infer from category if not stated: Fabric→M, Label/Button→PCS, Thread→M
12. "remark"          : any notes, special instructions, or requirements for this item
13. "source_ref"      : WHERE you found this — describe the table/section/column
                        (e.g. "BOM Table Row 5", "Trim Spec Section Row 3", "Accessories Table")
                        REQUIRED — never null

CRITICAL RULES — keep every value in its OWN field (do not swap columns):
- Extract EVERY row, even if some fields are missing
- material_code: look for alphanumeric codes, numbers with X suffix, # codes (e.g. #FT770ES),
  article numbers, item references. Weight (90g) and weave count (160X136) are NOT codes.
- supplier: the vendor/brand name (e.g. "TESSELLATION", "EAP", "YKK"). It goes ONLY in
  "supplier" — NEVER copy the supplier name into "spec", "color", or "placement".
- placement: a LOCATION on the garment ONLY (e.g. "Center Back Neck", "Side Seam", "CF Placket").
  A quantity like "1Ea", "1Pcs", "2 PCS" is NOT a placement → it belongs in "consumption".
- color: ONLY an explicit color instruction (DTM, White, Navy, N2, W2, Cream White). NONE of
  these are a color → return null: a spec ("13~14 SPI", "18L", "160X136"), a weight, a supplier
  name, or a placeholder phrase ("no color mentioned", "N/A"). If unclear → null (never a sentence).
- consumption: ONLY numeric quantity + unit per garment (e.g. "1 PCS", "1.35 M"). Fabric weight
  (g/m2), weave count (160X136), stitch density (SPI) or spec text are NOT consumption. If the
  quantity was written in another column, still put it HERE, not in placement.
- spec: technical composition ONLY (weight, composition, weave, ligne, finish, e.g. "POLY 60/2",
  "18L", "100% Cotton Twill"). NEVER put the supplier name, a remark/instruction sentence, a
  quantity, or a placement into "spec". A care-label instruction or note belongs in "remark".
- If the same item appears for multiple colorways with different colors, create ONE row
  and use the "colorways" object instead of "color"
- CODE IN ANY COLUMN: when the CODE column is empty, the material_code often sits in
  another column of the same row (even the color/colorway column, next to a ligne size
  like "18L"). Any long alphanumeric token (≥7 chars, mostly digits, often ending in X)
  in the row IS the material_code — capture it.
- THREAD TICKET CODES: a THREAD row's code may be a bare 3-digit ticket number (e.g.
  602, 603) in the CODE column. That IS the material_code — do not discard it.
- NEVER invent data not present in the text

BOM SECTION TITLE: {section_title}

BOM SECTION TEXT:
{section_text}

Return JSON:
{{
  "items": [
    {{
      "material_name":  "Body Fabric",
      "material_code":  null,
      "supplier":       "TESSELLATION",
      "supplier_code":  null,
      "category":       "FABRIC/YARN",
      "spec":           "100% Cotton Twill 160X136 70X80, Royal, Looseness Finishing & ECO Wash",
      "placement":      "Body",
      "color":          null,
      "colorways":      {{"N2": "HL2025-39751N", "W2": "HL2025-39748N"}},
      "consumption":    null,
      "unit":           "M",
      "remark":         null,
      "source_ref":     "Fabric Specification Table Row 1"
    }}
  ]
}}
"""

_ENRICH_PROMPT = """
You have materials extracted from the BOM section of a Tech Pack.
Some fields are missing (null).

Your task: Search the FULL DOCUMENT TEXT below for any additional information
about the specific materials listed.

For each material, look for:
- Any mention of the material name (exact or similar)
- Associated codes, article numbers, reference numbers
- Supplier / brand names
- Color information or colorway-specific colors
- Consumption / quantity data
- Placement / location on garment
- Technical specifications
- Remarks, notes, special instructions

MATERIALS NEEDING ENRICHMENT:
{materials_needing_enrichment}

FULL DOCUMENT TEXT:
{full_text}

Return JSON with ONLY the additional fields found (do not repeat already-filled fields):
{{
  "enrichments": [
    {{
      "material_name": "Care Label",
      "found_fields": {{
        "material_code": "111086874X",
        "supplier":      "EAP",
        "consumption":   "1 PCS",
        "remark":        "26SS NEW CARE LABEL — Side Seam"
      }},
      "sources": {{
        "material_code": "Label Specification section, code column",
        "supplier":      "Label Specification section, vendor column"
      }}
    }}
  ]
}}

Rules:
- Only return findings with clear evidence in the text
- Provide source citation for every found field
- If nothing additional is found for a material, omit it from the response
- Do NOT invent or guess values
"""


class MaterialExtractor:
    """
    Phase 2: Extracts all materials from BOM sections and cross-references
    the full document to fill missing fields.

    Input : DocumentMap from DocumentAnalyzer
    Output: List[Dict] — canonical material objects with per-field traceability
    """

    def __init__(self):
        self.llm = GroqClient()

    def extract(self, doc_map: Dict[str, Any]) -> List[Dict]:
        """
        Full extraction: BOM parse → dedup → cross-reference enrichment.

        Returns list of canonical material dicts with per-field source citations.
        """
        bom_sections = doc_map.get("bom_sections") or []
        full_text    = doc_map.get("full_text") or ""
        colorways    = doc_map.get("colorways") or []

        # Pass A: extract from each BOM section
        all_items: List[Dict] = []
        for section in bom_sections:
            items = self._extract_from_section(
                section.get("title", "BOM"),
                section.get("content", ""),
            )
            all_items.extend(items)

        logger.info(f"MaterialExtractor Pass A: {len(all_items)} items from {len(bom_sections)} BOM sections")

        if not all_items:
            logger.warning("MaterialExtractor: no items extracted from BOM sections")
            return []

        # Dedup: merge rows with same name + placement
        all_items = self._deduplicate(all_items)

        # Inject global colorways if not set at item level
        if colorways:
            for item in all_items:
                if not item.get("colorways") and not item.get("color") and item.get("category") in (
                    "FABRIC/YARN", "THREAD & BUTTON", "INTERLINING"
                ):
                    # Flag: colorway info may exist in full doc
                    item["_needs_colorway_enrich"] = True

        # Pass B: cross-reference full document for missing fields
        items_needing_enrich = self._find_items_needing_enrichment(all_items)
        if items_needing_enrich and full_text:
            enrichments = self._cross_reference(items_needing_enrich, full_text)
            all_items = self._apply_enrichments(all_items, enrichments)
            logger.info(f"MaterialExtractor Pass B: enriched {len(enrichments)} items")

        logger.info(f"MaterialExtractor: final {len(all_items)} canonical materials")
        return all_items

    # ── Pass A: BOM extraction ────────────────────────────────────────────────

    def _extract_from_section(self, section_title: str, section_text: str) -> List[Dict]:
        """Extract all material items from one BOM section text."""
        if not section_text or not section_text.strip():
            return []

        # If section is very long, split into overlapping chunks
        chunks = self._smart_chunk(section_text, max_chars=8000)
        items = []
        for chunk in chunks:
            chunk_items = self._llm_extract(section_title, chunk)
            items.extend(chunk_items)
        return items

    def _llm_extract(self, section_title: str, text: str) -> List[Dict]:
        try:
            prompt = _EXTRACT_PROMPT.format(
                section_title=section_title,
                section_text=text,
            )
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=2,
            )
            items = []
            if isinstance(result, list):
                items = result
            elif isinstance(result, dict):
                items = result.get("items") or result.get("trim_items") or []
            return [i for i in items if isinstance(i, dict) and i.get("material_name")]
        except Exception as e:
            logger.warning(f"MaterialExtractor LLM extract error: {e}")
            return []

    # ── Pass B: Cross-reference enrichment ───────────────────────────────────

    def _find_items_needing_enrichment(self, items: List[Dict]) -> List[Dict]:
        """Return items that have at least one empty critical field."""
        critical = ("material_code", "supplier", "color", "colorways", "consumption")
        return [
            item for item in items
            if any(not item.get(f) for f in critical)
        ]

    def _cross_reference(self, items_needing: List[Dict], full_text: str) -> List[Dict]:
        """
        Ask LLM to search the full document for missing fields.
        Batches up to 15 items per call to stay within token budget.
        """
        enrichments = []
        batch_size = 15

        for i in range(0, len(items_needing), batch_size):
            batch = items_needing[i: i + batch_size]
            batch_enrichments = self._llm_enrich(batch, full_text)
            enrichments.extend(batch_enrichments)

        return enrichments

    def _llm_enrich(self, items: List[Dict], full_text: str) -> List[Dict]:
        # Summarize what's missing for each item
        summary_lines = []
        for item in items:
            missing = [
                f for f in ("material_code", "supplier", "color", "colorways", "consumption", "remark")
                if not item.get(f)
            ]
            if missing:
                summary_lines.append(
                    f'- "{item["material_name"]}" (category: {item.get("category", "?")}, '
                    f'missing: {", ".join(missing)})'
                )

        if not summary_lines:
            return []

        try:
            prompt = _ENRICH_PROMPT.format(
                materials_needing_enrichment="\n".join(summary_lines),
                full_text=full_text[:7_000],   # trimmed to cut tokens (enrich is a fallback)
            )
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=1,
            )
            return result.get("enrichments") or []
        except Exception as e:
            logger.warning(f"MaterialExtractor cross-reference error: {e}")
            return []

    def _apply_enrichments(self, items: List[Dict], enrichments: List[Dict]) -> List[Dict]:
        """Merge enrichment results back into the canonical items."""
        enrich_index: Dict[str, Dict] = {
            (e.get("material_name") or "").lower().strip(): e
            for e in enrichments
            if isinstance(e, dict) and e.get("material_name")
        }

        for item in items:
            key = (item.get("material_name") or "").lower().strip()
            enrich = enrich_index.get(key)
            if not enrich:
                continue

            found = enrich.get("found_fields") or {}
            sources = enrich.get("sources") or {}

            # Only fill MISSING fields — never overwrite what BOM already provided
            for field, value in found.items():
                if value and not item.get(field):
                    item[field] = value
                    # Track enrichment source
                    source_key = f"_source_{field}"
                    item[source_key] = sources.get(field, "Document cross-reference")

        return items

    # ── Deduplication ─────────────────────────────────────────────────────────

    def _deduplicate(self, items: List[Dict]) -> List[Dict]:
        """
        Merge duplicate items (same material_name + placement) that were
        extracted from overlapping chunks.
        """
        seen: Dict[str, int] = {}  # key → index in result
        result: List[Dict] = []

        for item in items:
            key = (
                (item.get("material_name") or "").lower().strip(),
                (item.get("placement") or "").lower().strip(),
            )
            if key in seen:
                # Merge: fill empty fields of existing item
                existing = result[seen[key]]
                for field, value in item.items():
                    if value and not existing.get(field):
                        existing[field] = value
            else:
                seen[key] = len(result)
                result.append(item)

        return result

    # ── Chunking ──────────────────────────────────────────────────────────────

    @staticmethod
    def _smart_chunk(text: str, max_chars: int = 8000) -> List[str]:
        """Split text into chunks, preferring line boundaries."""
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
