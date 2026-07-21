"""
document_analyzer.py — Phase 1: Semantic Document Understanding

Reads the ENTIRE Tech Pack text and builds a semantic map of what each
section contains.  Zero hardcoded page numbers, company names, keywords,
or layout assumptions.

The LLM reasons about CONTENT, not POSITION.
Works identically for HAZZYS, Uniqlo, Zara, Nike, or any future customer.
"""
import logging
from typing import Any, Dict, List

from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

# ── LLM Prompts ───────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a document intelligence agent specialized in garment Tech Packs. "
    "Return valid JSON only. No markdown, no explanation."
)

_STRUCTURE_PROMPT = """
Analyze the garment Tech Pack text below.

YOUR TASK: Identify every distinct semantic section and classify its purpose.

SECTION TYPES (use exactly these labels):
- BOM            : Bill of Materials, Material List, Trim List, Accessories List, Components
- COLORWAY       : Colorway table, color options, color-per-size, fabric color variants
- MEASUREMENT    : Size chart, body measurements, grading, size spec
- CONSTRUCTION   : Sewing instructions, stitch type, seam allowance, construction detail
- LABEL_SPEC     : Label artwork, label size, label placement diagram, label content
- PACKING_SPEC   : Packing instructions, carton dimensions, folding method, packing materials
- CARE           : Care instructions, washing symbols, maintenance guide
- TESTING        : Testing requirements, quality standards, compliance
- STYLE_HEADER   : Cover page, style info, buyer info, season, PO number
- COMMENT        : Notes, special instructions, factory comments
- OTHER          : Anything not covered above

For each section provide:
1. "type"    : one of the labels above
2. "title"   : the heading or label as it appears in the document (or best guess)
3. "summary" : 1-sentence description of what this section contains
4. "excerpt" : the first 200 characters of that section's text (verbatim, for traceability)

Also extract at the top level:
- "colorways"       : list of colorway codes/names found anywhere in the document (e.g. ["N2","W2"] or ["Navy","White"])
- "bom_total_lines" : integer — if the document states a total number of BOM/trim rows, capture it; else null
- "style_info"      : brief object with any globally-found style_code, buyer, season, garment_type (null if not found)

Return JSON:
{{
  "sections": [
    {{
      "type":    "BOM",
      "title":   "EXPECTED TRIM LIST",
      "summary": "Main bill of materials table with 18 trim items",
      "excerpt": "EXPECTED TRIM LIST\\nNo. Description Supplier Code..."
    }},
    {{
      "type":    "COLORWAY",
      "title":   "COLOR OPTIONS",
      "summary": "Two colorways: N2 Navy and W2 White",
      "excerpt": "COLOR OPTIONS\\nN2 — Navy Blue\\nW2 — White..."
    }}
  ],
  "colorways":       ["N2", "W2"],
  "bom_total_lines": 18,
  "style_info": {{
    "style_code":    "HZSH-6C331",
    "buyer":         null,
    "season":        "2026FW",
    "garment_type":  "Men Woven Shirt"
  }}
}}

TECH PACK TEXT:
{text}
"""

_SECTION_CONTENT_PROMPT = """
Below is text from a garment Tech Pack.
A previous analysis identified these sections as BOM/material-related:
{section_titles}

Extract the RAW TEXT that corresponds to each BOM section from the full document.
Return JSON:
{{
  "bom_sections": [
    {{
      "title":   "EXPECTED TRIM LIST",
      "content": "<verbatim text of that BOM section>"
    }}
  ]
}}

FULL DOCUMENT:
{text}
"""


class DocumentAnalyzer:
    """
    Phase 1: Maps the semantic structure of a Tech Pack.

    Input : raw text of the full Tech Pack (any format, any brand)
    Output: DocumentMap with identified sections, colorways, style info
    """

    def __init__(self):
        self.llm = GroqClient()

    def analyze(self, raw_text: str) -> Dict[str, Any]:
        """
        Semantically analyze the full document.

        Returns:
        {
          "sections":        List[{type, title, summary, excerpt}],
          "bom_sections":    List[{title, content}],   ← BOM text extracted
          "colorways":       List[str],
          "bom_total_lines": int | None,
          "style_info":      {style_code, buyer, season, garment_type} | None,
          "full_text":       str,   ← kept for cross-reference in Phase 2
        }
        """
        logger.info("DocumentAnalyzer: starting semantic structure analysis")

        # Phase 1a — structure discovery (send up to 20K chars; enough for any TP)
        structure = self._discover_structure(raw_text[:20_000])

        sections        = structure.get("sections") or []
        colorways       = structure.get("colorways") or []
        bom_total_lines = structure.get("bom_total_lines")
        style_info      = structure.get("style_info") or {}

        logger.info(
            f"DocumentAnalyzer: found {len(sections)} sections — "
            f"colorways={colorways}, bom_lines={bom_total_lines}"
        )

        # Phase 1b — extract the actual text content of BOM sections
        bom_sections = self._extract_bom_text(raw_text, sections)

        logger.info(f"DocumentAnalyzer: {len(bom_sections)} BOM sections extracted")

        return {
            "sections":        sections,
            "bom_sections":    bom_sections,
            "colorways":       colorways,
            "bom_total_lines": bom_total_lines,
            "style_info":      style_info,
            "full_text":       raw_text,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _discover_structure(self, text: str) -> Dict:
        prompt = _STRUCTURE_PROMPT.format(text=text)
        try:
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=2,
            )
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning(f"DocumentAnalyzer: structure discovery failed: {e}")
        return {"sections": [], "colorways": [], "bom_total_lines": None, "style_info": None}

    def _extract_bom_text(self, full_text: str, sections: List[Dict]) -> List[Dict]:
        """
        For each section classified as BOM, extract its text content.
        Strategy: LLM identifies content, fallback to excerpt-based search.
        """
        bom_sections_meta = [s for s in sections if s.get("type") == "BOM"]
        if not bom_sections_meta:
            # No explicit BOM identified — treat the whole document as one BOM
            logger.info("DocumentAnalyzer: no BOM section found — using full text")
            return [{"title": "Full Document", "content": full_text}]

        # For each BOM section, locate and extract its text
        bom_sections = []
        for meta in bom_sections_meta:
            content = self._locate_section_text(full_text, meta)
            if content:
                bom_sections.append({"title": meta.get("title", "BOM"), "content": content})

        if not bom_sections:
            # Fallback: all BOM excerpts concatenated
            all_excerpts = "\n\n".join(
                m.get("excerpt", "") for m in bom_sections_meta if m.get("excerpt")
            )
            return [{"title": "BOM (excerpt)", "content": all_excerpts or full_text}]

        return bom_sections

    # BOM section keywords — any of these signals a material/trim list
    _BOM_KEYWORDS = [
        "bom (bill of material", "bill of material", "trim list",
        "accessories list", "material list", "expected trim",
        "trims\n", "trims ",
    ]

    def _locate_section_text(self, full_text: str, section_meta: Dict) -> str:
        """
        Find the actual text of a section using its excerpt as a locator anchor.
        Tries multiple strategies before falling back to LLM.
        """
        full_lower = full_text.lower()
        content_size = 12000  # chars to extract from anchor point

        # Attempt 1: find by excerpt anchor (verbatim, no LLM)
        excerpt = (section_meta.get("excerpt") or "").strip()
        if excerpt and len(excerpt) > 20:
            # Strip trailing ellipsis that LLM may add
            anchor = excerpt[:80].rstrip(".").strip()
            idx = full_text.find(anchor)
            if idx == -1:
                idx = full_lower.find(anchor.lower())
            if idx != -1:
                return full_text[idx: idx + content_size]

        # Attempt 2: search by title (word-by-word fallback)
        title = (section_meta.get("title") or "").strip()
        if title and len(title) > 3:
            idx = full_lower.find(title.lower())
            if idx != -1:
                return full_text[idx: idx + content_size]
            # Try each significant word from title (≥5 chars)
            for word in title.split():
                if len(word) >= 5:
                    idx = full_lower.find(word.lower())
                    if idx != -1:
                        return full_text[idx: idx + content_size]

        # Attempt 3: BOM keyword scan (catches "BOM (BILL OF MATERIAL)", "TRIMS", etc.)
        sec_type = (section_meta.get("type") or "").upper()
        if sec_type == "BOM":
            for kw in self._BOM_KEYWORDS:
                idx = full_lower.find(kw)
                if idx != -1:
                    return full_text[idx: idx + content_size]

        # Attempt 4: ask LLM to find and extract it
        return self._llm_extract_section(full_text, section_meta)

    def _llm_extract_section(self, full_text: str, section_meta: Dict) -> str:
        """LLM fallback: extract section text when anchor search fails."""
        try:
            prompt = _SECTION_CONTENT_PROMPT.format(
                section_titles=f'- {section_meta.get("title")}: {section_meta.get("summary")}',
                text=full_text[:15_000],
            )
            result = self.llm.extract_json(system_prompt=_SYSTEM, user_content=prompt)
            sections = result.get("bom_sections") or []
            if sections:
                return sections[0].get("content") or ""
        except Exception as e:
            logger.warning(f"DocumentAnalyzer: LLM section extraction failed: {e}")
        return ""
