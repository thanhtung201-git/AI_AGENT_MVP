"""
normalizer.py — Step 1.5: Clean and normalize raw LLM extraction output.

Runs AFTER TechPackExtractor, BEFORE TrimMasterMapper.

Problems solved:
  1. Color codes (N2, W2, DTM) ending up in the consumption field
  2. Unit defaulting to "pcs" regardless of category
  3. Consumption containing non-numeric garbage
  4. Material name carrying redundant spec text
  5. Category misclassification from LLM

No LLM calls — pure deterministic normalization rules.
"""
import re
import logging
from typing import List, Optional, Tuple

from backend.trimlist.traceability import TrimRow, CATEGORY_ORDER, classify_category

logger = logging.getLogger(__name__)

# ── Color pattern detection ───────────────────────────────────────────────────
# Matches: N2, W2, K1, BK1, WH2, DTM, "TO MATCH", "AS PER FABRIC", etc.
# Weave count pattern (e.g. 160X136, 70X80) — NOT a consumption or color
_WEAVE_COUNT_RE = re.compile(r"\b\d{2,3}[Xx]\d{2,3}\b")

# Spec-text signals in color field — if any hit, color is contaminated spec text
_SPEC_IN_COLOR_RE = re.compile(
    r"\d{2,3}[Xx]\d{2,3}"         # weave count
    r"|\d+\s*(?:g|gsm|g/m)"       # fabric weight
    r"|\d+\s*(?:~|-)?\s*\d*\s*SPI" # stitch density e.g. "13~14 SPI"
    r"|\d+\s*L\b"                  # ligne size e.g. "18L", "14L"
    r"|TWILL|SATIN|HERRINGBONE|OXFORD|POPLIN|FLANNEL|JERSEY|DENIM"
    r"|COMPOSITION|FINISHING|LOOSENESS|QUALITY\s+\d",
    re.IGNORECASE,
)

# Placeholder phrases an LLM leaks into color instead of returning null.
_COLOR_PLACEHOLDER_RE = re.compile(
    r"^\s*(no\s+color(\s+mentioned)?|not\s+mentioned|no\s+mention|n/?a|none|unknown|tbd|-)\s*$",
    re.IGNORECASE,
)

# A placement cell that is really a quantity (LLM put the qty in the wrong column).
_QTY_ONLY_RE = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*(pcs?|pc|ea|set|m|yds?|cm|mm|cone|roll)\s*$",
    re.IGNORECASE,
)

_COLOR_RE = re.compile(
    r"\b([A-Z]{1,3}\d{1,2})\b"                # N2, W2, BK1, WH2
    r"|\bDTM\b"                                 # Dye To Match
    r"|\bTO\s+MATCH\b"                          # To Match
    r"|\bAS\s+PER\s+(FABRIC|DESIGN|SAMPLE)\b",  # As per fabric/design
    re.IGNORECASE,
)

# ── Consumption value detection ────────────────────────────────────────────────
# Matches: "1.35 M", "2 PCS", "0.5 YDS", "300 CM", "1 CONE", "1 ROLL"
_CONSUMPTION_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(m\b|yds?\b|yards?\b|kg\b|cm\b|mm\b|pcs?\b|pc\b|ea\b|set\b|cone\b|roll\b|spool\b)",
    re.IGNORECASE,
)

# ── Category-aware default units ───────────────────────────────────────────────
_UNIT_DEFAULTS = {
    "FABRIC/YARN":     "M",
    "INTERLINING":     "M",
    "THREAD & BUTTON": "PCS",   # refined per name below
    "LABEL":           "PCS",
    "PACKING":         "PCS",
    "OTHER":           "PCS",
}

# Within THREAD & BUTTON, sub-classify by name
_THREAD_KEYWORDS  = ["thread", "sewing thread", "yarn thread", "polyester thread", "cotton thread"]
_ZIPPER_KEYWORDS  = ["zipper", "zip", "fly zip", "pocket zip"]
_CORD_KEYWORDS    = ["drawcord", "cord", "ribbon", "tape", "elastic", "braid", "binding"]
_BUTTON_KEYWORDS  = ["button", "bttn", "snap", "hook", "eye", "rivet", "stud"]

# ── Unit normalization map ─────────────────────────────────────────────────────
_UNIT_NORMALIZE = {
    "pcs": "PCS", "pc": "PCS", "ea": "PCS", "set": "SET",
    "m": "M", "metre": "M", "meter": "M", "mtrs": "M",
    "yds": "YDS", "yd": "YDS", "yards": "YDS", "yard": "YDS",
    "kg": "KG", "gram": "G", "g": "G",
    "cm": "CM", "mm": "MM",
    "cone": "CONE", "roll": "ROLL", "spool": "CONE",
}


class TrimNormalizer:
    """
    Post-extraction normalization.

    Pass List[TrimRow] from TechPackExtractor → returns cleaned List[TrimRow].
    No external calls. Pure deterministic.
    """

    def normalize(self, rows: List[TrimRow]) -> List[TrimRow]:
        before = len(rows)
        for row in rows:
            self._fix_category(row)
            self._separate_color_from_consumption(row)
            self._normalize_consumption(row)
            self._normalize_unit(row)
            self._normalize_color(row)
            self._normalize_placement(row)
            self._normalize_spec(row)
        logger.info(f"TrimNormalizer: normalized {before} rows")
        return rows

    # ── Step 1: Fix category ──────────────────────────────────────────────────

    def _fix_category(self, row: TrimRow) -> None:
        """Re-classify category if it's missing or invalid."""
        if row.category not in CATEGORY_ORDER:
            row.category = classify_category(row.material_name)
            row.sort_key  = CATEGORY_ORDER.get(row.category, 99)

    # ── Step 2: Separate color from consumption ───────────────────────────────

    def _separate_color_from_consumption(self, row: TrimRow) -> None:
        """
        LLM sometimes puts "N2" or "DTM" into the consumption field.
        Detect color codes in consumption and move them to the color field.

        Example:
          consumption="N2"            → consumption=None,  color="N2"
          consumption="1.35 M / N2"   → consumption="1.35 M", color="N2"
          consumption="DTM"           → consumption=None,  color="DTM"
        """
        if not row.consumption:
            return

        raw = row.consumption.strip()
        color_found, cleaned_consumption = self._extract_color(raw)

        if color_found:
            # Move color to the color field if not already set
            if not row.color:
                row.color = color_found
            # Update consumption to the cleaned version (may be empty)
            row.consumption = cleaned_consumption if cleaned_consumption else None
            logger.debug(
                f"TrimNormalizer: moved '{color_found}' from consumption to color "
                f"for '{row.material_name}'"
            )

    def _extract_color(self, text: str) -> Tuple[Optional[str], str]:
        """
        Extract color code from text. Returns (color_found, remaining_text).
        """
        colors_found = []
        cleaned = text

        for match in _COLOR_RE.finditer(text):
            colors_found.append(match.group().upper())
            # Remove matched color from the string
            cleaned = cleaned[:match.start()] + " " + cleaned[match.end():]

        # Clean up remaining text: remove separators, extra spaces
        cleaned = re.sub(r"[/|,\s]+", " ", cleaned).strip()
        cleaned = re.sub(r"^[-/|,\s]+|[-/|,\s]+$", "", cleaned).strip()

        color = " / ".join(colors_found) if colors_found else None
        return color, cleaned

    # ── Step 3: Normalize consumption ─────────────────────────────────────────

    def _normalize_consumption(self, row: TrimRow) -> None:
        """
        Normalize consumption to format: "1.35 M", "2 PCS", "0.25 YDS".
        Extract unit into row.unit if consumption contains a unit.
        """
        if not row.consumption:
            return

        raw = row.consumption.strip()

        # Reject weave counts (160X136, 70X80) — these are NOT consumption
        if _WEAVE_COUNT_RE.search(raw):
            row.consumption = None
            return

        match = _CONSUMPTION_RE.search(raw)
        if not match:
            # Consumption has no recognizable value — might be garbage text
            # Check if it's just a number
            num_match = re.search(r"(\d+(?:[.,]\d+)?)", raw)
            if num_match:
                qty = num_match.group(1).replace(",", ".")
                row.consumption = qty  # keep number, unit will be set by normalize_unit
            else:
                row.consumption = None  # discard unrecognizable consumption
            return

        qty = match.group(1).replace(",", ".")
        unit_raw = match.group(2).lower().strip()
        unit_norm = _UNIT_NORMALIZE.get(unit_raw, unit_raw.upper())

        row.consumption = f"{qty} {unit_norm}"
        # Also update unit field if it's still at default
        if not row.unit or row.unit.lower() == "pcs":
            row.unit = unit_norm

    # ── Step 4: Normalize unit ─────────────────────────────────────────────────

    def _normalize_unit(self, row: TrimRow) -> None:
        """Set unit based on category and material name keywords."""
        # Already has a meaningful unit (not default pcs)
        if row.unit and row.unit.upper() not in ("PCS", "PC", ""):
            row.unit = _UNIT_NORMALIZE.get(row.unit.lower(), row.unit.upper())
            return

        # Determine correct unit from category + name
        row.unit = self._infer_unit(row.category, row.material_name)

    def _infer_unit(self, category: str, name: str) -> str:
        name_lower = (name or "").lower()

        if category == "FABRIC/YARN":
            return "M"

        if category == "INTERLINING":
            return "M"

        if category == "THREAD & BUTTON":
            if any(kw in name_lower for kw in _THREAD_KEYWORDS):
                return "M"
            if any(kw in name_lower for kw in _CORD_KEYWORDS):
                return "M"
            # Buttons, zippers, snaps → PCS
            return "PCS"

        if category == "LABEL":
            return "PCS"

        if category == "PACKING":
            return "PCS"

        return "PCS"  # default for OTHER

    # ── Step 5: Normalize color ───────────────────────────────────────────────

    def _normalize_color(self, row: TrimRow) -> None:
        """
        Standardize color values:
          "dtm" → "DTM"
          "to match" → "DTM"
          "white" → "White"
          "n2" → "N2"
        """
        if not row.color:
            return

        c = row.color.strip()

        # Reject LLM placeholder phrases ("no color mentioned", "N/A", "-")
        if _COLOR_PLACEHOLDER_RE.match(c):
            row.color = None
            return

        # Reject spec text contamination in color field ("13~14 SPI", "18L", weave…)
        if _SPEC_IN_COLOR_RE.search(c):
            row.color = None
            return

        # Supplier name leaked into color (e.g. "TESSELLATION")
        if row.supplier and c.lower() == row.supplier.strip().lower():
            row.color = None
            return

        # Normalize "to match" / "match fabric" → DTM
        if re.search(r"to\s+match|match\s+(fabric|garment|body)", c, re.IGNORECASE):
            row.color = "DTM"
            return

        # Uppercase Korean codes (N2, W2, BK1, etc.)
        if re.fullmatch(r"[A-Z]{1,3}\d{1,2}", c.upper()):
            row.color = c.upper()
            return

        # "DTM" variants
        if c.upper() in ("DTM", "D.T.M", "DYE TO MATCH"):
            row.color = "DTM"
            return

        # Title-case regular color names
        if c.upper() in ("WHITE", "BLACK", "NAVY", "GREY", "GRAY", "BEIGE", "BROWN", "RED"):
            row.color = c.title()
            return

        # Leave as-is otherwise
        row.color = c

    # ── Step 6: Normalize placement ───────────────────────────────────────────

    def _normalize_placement(self, row: TrimRow) -> None:
        """
        Convert overly generic placements to more specific ones where possible.
        E.g., "collar" → "Collar Upper Layer" is too much of a guess,
        but we can at least Title-case and trim whitespace.
        Specific placement must come from Tech Pack / LLM extraction.
        """
        if not row.placement:
            return
        p = row.placement.strip()

        # A quantity landed in placement (LLM column swap). Move it to consumption
        # (if empty) and clear placement — placement must be a location, not a count.
        if _QTY_ONLY_RE.match(p):
            if not row.consumption:
                row.consumption = p
            row.placement = None
            return

        # Title-case and strip
        row.placement = p.title()

    # ── Step 7: Normalize spec / composition ──────────────────────────────────

    def _normalize_spec(self, row: TrimRow) -> None:
        """COMPOSITION column = spec. Strip values that are clearly NOT a composition:
        the supplier name, placeholder text, or a bare quantity."""
        if not row.spec:
            return
        s = row.spec.strip()
        if row.supplier and s.lower() == row.supplier.strip().lower():
            row.spec = None
            return
        if _COLOR_PLACEHOLDER_RE.match(s) or _QTY_ONLY_RE.match(s):
            row.spec = None
