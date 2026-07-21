"""
raw_line_extractor.py — Phase 1.5: Verbatim raw-line transcription (anti-miss pass).

Why a separate pass
-------------------
LLMs drop rows when they read AND classify in the same step. So we split it:
  PASS 1 (here)  — copy EVERY material/trim line verbatim, in page order, with NO
                   classification, NO summarizing, NO shortening of compound names.
  PASS 2 (MaterialExtractor) — classify / build the structured table.

The verbatim list becomes the ground truth the pipeline later reconciles the final
trimlist against (reconciliation.py): every raw line MUST appear in the output, or it
is recovered / flagged. Zero hardcoded names — works for any brand's Tech Pack.

temperature=0 → the raw list is stable across runs (no "one more item each time").
"""
import logging
import re
from typing import Any, Dict, List

from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a meticulous transcription clerk for garment Tech Packs. You copy text "
    "EXACTLY as written. You never summarize, classify, merge, shorten, or invent. "
    "Return valid JSON only."
)

_RAW_PROMPT = """
Below is the material / BOM / trim section text of a garment Tech Pack.

YOUR ONLY JOB: transcribe EVERY material or trim entry as a separate line, VERBATIM,
in the exact order it appears. This is a copy step — do NOT classify, do NOT build a
table, do NOT summarize, do NOT deduplicate.

STRICT RULES:
- One output line per material/trim entry (a row that names a physical item:
  fabric, interlining, thread, button, label, tag, sticker, band, clip, bag, box, etc.).
- Copy the FULL name text of the entry, including codes/qty/notes on that line.
- NEVER shorten or genericize a compound name. Keep it whole, character for character.
  e.g. keep "1st Main Tag + 2nd Main Tag (Price Tag) & Tag Hook" — do NOT reduce it to
  "hangtag". Keep "THREAD - Shrank thread" — do NOT reduce it to "Thread".
- Keep every repeated entry (e.g. the same "Thread" on 7 different placements = 7 lines).
- SKIP only pure table-header rows (column titles like "NO | DESCRIPTION | CODE | QTY")
  and section-title / separator rows. Keep everything that is an actual item.
- Do NOT add items that are not in the text.

MATERIAL / BOM TEXT:
{bom_text}

Return JSON — a flat list, order preserved:
{{
  "raw_lines": [
    "1. Body Fabric  100% Cotton Twill 160X136  TESSELLATION  Pls see T/P",
    "INTERLINING FT770ES  collar upper layer/ inner collar band/ cuff  TESSELLATION",
    "THREAD - Shrank thread  603  BUTTON",
    "1st Main Tag + 2nd Main Tag (Price Tag) & Tag Hook  222042553X",
    "RFID Tag  UHZTGR00200  LF  On back side of Care Label"
  ]
}}
"""


class RawLineExtractor:
    """Pass 1: verbatim transcription of every material/trim line."""

    def __init__(self):
        self.llm = GroqClient()

    def extract(self, bom_sections: List[Dict]) -> Dict[str, Any]:
        """
        Args:
            bom_sections: [{title, content}] from DocumentAnalyzer.

        Returns:
            {"raw_lines": List[str], "count": int, "by_section": {title: n}}
        """
        raw_lines: List[str] = []
        by_section: Dict[str, int] = {}

        for section in bom_sections:
            title   = section.get("title", "BOM")
            content = section.get("content", "")
            lines   = self._transcribe(content)
            by_section[title] = len(lines)
            raw_lines.extend(lines)

        # Drop exact-duplicate blank/again lines but KEEP legitimate repeats
        # (same item on different placements has different full text).
        cleaned = [ln.strip() for ln in raw_lines if ln and ln.strip()]

        logger.info(f"RawLineExtractor: {len(cleaned)} raw lines from {len(bom_sections)} section(s)")
        return {"raw_lines": cleaned, "count": len(cleaned), "by_section": by_section}

    def _transcribe(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []
        out: List[str] = []
        for chunk in self._chunk(text, max_chars=8000):
            try:
                result = self.llm.extract_json(
                    system_prompt=_SYSTEM,
                    user_content=_RAW_PROMPT.format(bom_text=chunk),
                    temperature=0.0,   # verbatim copy must be stable
                )
                lines = result.get("raw_lines") if isinstance(result, dict) else result
                if isinstance(lines, list):
                    out.extend(str(x).strip() for x in lines if str(x).strip())
            except Exception as e:
                logger.warning(f"RawLineExtractor transcribe error: {e}")
        return out

    @staticmethod
    def _chunk(text: str, max_chars: int) -> List[str]:
        if len(text) <= max_chars:
            return [text]
        chunks, cur = [], ""
        for line in text.splitlines(keepends=True):
            if len(cur) + len(line) > max_chars and cur:
                chunks.append(cur)
                cur = line
            else:
                cur += line
        if cur:
            chunks.append(cur)
        return chunks


# ── shared token helper (used by reconciliation) ─────────────────────────────

def name_tokens(s: str) -> set:
    """Distinctive lowercase alphanumeric tokens of a name/line, minus generic words."""
    toks = set(re.findall(r"[a-z0-9]+", (s or "").lower()))
    return toks - _GENERIC


# Words too generic to identify a specific material — excluded when matching a raw
# line to an output row, so "THREAD - Shrank thread" is judged by "shrank", not "thread".
_GENERIC = {
    "the", "for", "and", "with", "new", "pcs", "pc", "ea", "set", "of", "on", "to",
    "tag", "label", "thread", "fabric", "sticker", "material", "trim", "color",
    "colour", "size", "code", "qty", "no", "item", "1st", "2nd", "3rd", "part",
    "26ss", "26fw", "25ss", "25fw", "21fw", "24fw", "24ss",
}
