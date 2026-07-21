"""
branch_detector.py — Step 1 of Ana's process: read the Tech Pack to decide the
garment BRANCH (gender × construction), e.g. "Men Woven", "Ladies Knit".

Why it matters
--------------
The Trim Master packing file is organised into one sheet PER BRANCH
(Men Woven / Ladies Woven / Men Knit / Ladies Knit / Kids Woven …). Picking the
right branch is what lets us take the correct, complete packing list — instead of
merging every sheet (wrong-branch items) or letting the LLM guess a subset.

Design: infer deterministically from explicit keywords first (Tech Pack cover /
style description usually says "MEN'S ... WOVEN" or "WOMEN'S/LADIES' ... WOVEN").
Fall back to the LLM only for the parts that stay ambiguous. The result is meant to
be shown to the user pre-filled for a 1-click confirm — never silently trusted when
confidence is low, because the input does not always carry an explicit gender field.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

GENDERS      = ("Men", "Ladies", "Kids")
CONSTRUCTIONS = ("Woven", "Knit")

# Deterministic keyword signals. Ladies/Kids are checked before Men because the
# substring "men" hides inside "women" — order matters.
_GENDER_PATTERNS = [
    ("Kids",   r"\b(kids?|children|child|infant|toddler|baby|boys?|girls?)\b"),
    ("Ladies", r"\b(ladies|lady|women|woman|womens|female|w/s)\b|women'?s"),
    ("Men",    r"\b(men|mens|man|male|gentleman)\b|men'?s"),
]
_CONSTRUCTION_PATTERNS = [
    ("Woven", r"\bwoven\b"),
    ("Knit",  r"\b(knit|knitted|knitwear|jersey|sweater|cardigan|rib)\b"),
]


def _scan(text: str, patterns) -> tuple[Optional[str], str]:
    """Return (label, evidence-snippet) for the first pattern that hits."""
    low = text.lower()
    for label, pat in patterns:
        m = re.search(pat, low)
        if m:
            start = max(0, m.start() - 25)
            snippet = text[start:m.end() + 25].replace("\n", " ").strip()
            return label, snippet
    return None, ""


class BranchDetector:
    """Infer the garment branch from Tech Pack text (auto + confidence for confirm)."""

    def detect(self, text: str, style_info: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Returns:
        {
          "gender":       "Men" | "Ladies" | "Kids" | None,
          "construction": "Woven" | "Knit" | None,
          "branch_key":   "Men Woven" | ... | None,
          "confidence":   "high" | "medium" | "low",
          "evidence":     {"gender": "...", "construction": "..."},
          "source":       "keyword" | "llm" | "mixed",
        }
        """
        style_info = style_info or {}
        # Search the Tech Pack text plus any garment_type the analyzer already found.
        hay = " ".join(str(v) for v in (
            text or "", style_info.get("garment_type") or "", style_info.get("style_code") or "",
        ))

        gender, g_ev = _scan(hay, _GENDER_PATTERNS)
        constr, c_ev = _scan(hay, _CONSTRUCTION_PATTERNS)
        source = "keyword"

        # LLM fallback only for what stayed ambiguous. Its answer is accepted ONLY
        # when the quote it cites actually contains the word it claims to have read
        # — otherwise it is guessing. A Tech Pack that never states a gender must
        # come back as unknown, not as a coin flip: downstream picks the wrong Trim
        # Master sheet and every packing code is wrong.
        if not gender or not constr:
            llm = self._llm_infer(text[:6000], style_info)
            ev = str(llm.get("evidence") or "")
            if not gender and llm.get("gender") in GENDERS:
                if _scan(ev, _GENDER_PATTERNS)[0] == llm["gender"]:
                    gender, g_ev, source = llm["gender"], ev, "mixed"
                else:
                    logger.info(f"BranchDetector: rejected LLM gender '{llm['gender']}' — evidence has no gender word: {ev[:60]!r}")
            if not constr and llm.get("construction") in CONSTRUCTIONS:
                if _scan(ev, _CONSTRUCTION_PATTERNS)[0] == llm["construction"]:
                    constr, c_ev, source = llm["construction"], ev, "mixed"
                else:
                    logger.info(f"BranchDetector: rejected LLM construction '{llm['construction']}' — evidence has no construction word: {ev[:60]!r}")
            if source == "keyword":
                source = "llm"

        # Confidence: both from explicit keywords = high; any LLM/partial = medium; none = low
        if gender and constr:
            confidence = "high" if source == "keyword" else "medium"
        elif gender or constr:
            confidence = "low"
        else:
            confidence = "low"

        branch_key = f"{gender} {constr}" if gender and constr else None
        logger.info(f"BranchDetector: {branch_key} (confidence={confidence}, source={source})")

        return {
            "gender":       gender,
            "construction": constr,
            "branch_key":   branch_key,
            "confidence":   confidence,
            "evidence":     {"gender": g_ev, "construction": c_ev},
            "source":       source,
        }

    # ── LLM fallback ──────────────────────────────────────────────────────────

    def _llm_infer(self, text: str, style_info: Dict) -> Dict[str, Any]:
        try:
            from backend.utils.groq_client import GroqClient
            system = "You classify garment Tech Packs. Return valid JSON only."
            prompt = f"""From this garment Tech Pack, determine two things:
1. gender: one of "Men", "Ladies", "Kids" (Ladies = women/ladies).
2. construction: one of "Woven" or "Knit".

Only answer from evidence in the text. If truly unclear, use null.

STYLE INFO: {style_info}

TECH PACK TEXT:
{text}

Return JSON: {{"gender": "...", "construction": "...", "evidence": "<short quote>"}}"""
            result = GroqClient().extract_json(system_prompt=system, user_content=prompt, temperature=0.0)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.warning(f"BranchDetector LLM fallback error: {e}")
            return {}
