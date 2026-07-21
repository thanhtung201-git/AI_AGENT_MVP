"""
canonical_to_trimrow.py — Convert canonical material dicts → TrimRow objects.

The new pipeline produces rich canonical dicts with per-field traceability.
This module converts them to TrimRow for compatibility with the existing
excel_writer, validator, buyer_rule_engine, and email_override modules.
"""
import logging
from typing import Any, Dict, List, Optional

from backend.trimlist.traceability import TrimRow, TrimSource, CATEGORY_ORDER, classify_category

logger = logging.getLogger(__name__)

# Standard unit normalization — LLM may return varied casing
_UNIT_MAP = {
    "m": "M", "metre": "M", "meter": "M", "mtrs": "M", "mtr": "M",
    "yds": "YDS", "yd": "YDS", "yards": "YDS",
    "pcs": "PCS", "pc": "PCS", "ea": "PCS", "piece": "PCS",
    "kg": "KG", "g": "G", "gram": "G",
    "cm": "CM", "mm": "MM",
    "cone": "CONE", "roll": "ROLL", "spool": "CONE", "set": "SET",
}

# Default unit by category when LLM provides none
_DEFAULT_UNIT = {
    "FABRIC/YARN": "M",
    "INTERLINING": "M",
    "THREAD & BUTTON": "PCS",
    "LABEL": "PCS",
    "PACKING": "PCS",
    "OTHER": "PCS",
}


def canonical_to_trimrows(canonical_items: List[Dict]) -> List[TrimRow]:
    """
    Convert list of canonical material dicts (from MasterIntegrator output)
    to TrimRow objects compatible with the rest of the pipeline.
    """
    rows = []
    for item in canonical_items:
        row = _convert_one(item)
        if row is None:
            continue
        if _is_phantom(row):
            logger.info(f"canonical_to_trimrows: dropped phantom item '{row.material_name}'")
            continue
        rows.append(row)
    logger.info(f"canonical_to_trimrows: converted {len(rows)}/{len(canonical_items)} items")
    return rows


def _is_phantom(row: TrimRow) -> bool:
    """Not a material: a section header the LLM copied as a row ('INTERLINING'),
    or a remark it mistook for one ('26SS NEW QUALITY'). Either way it carries no
    code, no placement and no consumption — a real trim always has at least one."""
    if row.material_code or row.placement or row.consumption:
        return False
    from backend.trimlist.reconciliation import _SECTION_HEADERS
    if (row.material_name or "").strip().upper() in _SECTION_HEADERS:
        return True
    from backend.trimlist.raw_line_extractor import name_tokens
    return row.category == "OTHER" and len(name_tokens(row.material_name)) <= 1


def _convert_one(item: Dict) -> Optional[TrimRow]:
    name = (item.get("material_name") or "").strip()
    if not name:
        return None

    # Category
    category = _clean_category(item.get("category") or "")
    if category not in CATEGORY_ORDER:
        category = classify_category(name)
    if category == "OTHER":
        # LLM said OTHER but the name may classify cleanly ("stripe tape",
        # "Silica gel") — an unclassified row is an ERROR downstream.
        category = classify_category(name)

    # Unit
    unit_raw = (item.get("unit") or "").strip().lower()
    unit = _UNIT_MAP.get(unit_raw) or unit_raw.upper() or _DEFAULT_UNIT.get(category, "PCS")

    # Color / colorways
    raw_color = item.get("color")
    color_val = None if not raw_color or str(raw_color).strip().upper() in ("N/A", "NA", "NULL", "NONE", "-") else raw_color
    colorways_raw = item.get("colorways")
    if isinstance(colorways_raw, dict) and colorways_raw:
        colors = {k.upper(): v for k, v in colorways_raw.items() if k and v}
        color_val = None  # use colorways, not single color
    else:
        colors = {}

    # Consumption — normalize to "<number> <UNIT>"
    consumption = _normalize_consumption(item.get("consumption"))

    # Build source traceability from the "sources" dict
    sources: Dict[str, str] = item.get("sources") or {}
    enrich_sources = {
        k.replace("_source_", ""): v
        for k, v in item.items()
        if k.startswith("_source_") and v
    }
    all_sources = {**enrich_sources, **sources}  # sources from merge takes priority

    # Honest primary source: only claim TRIM_MASTER when there is REAL Master evidence
    # (an exact cell _loc, or a citation that mentions the master). Otherwise the item
    # is Tech-Pack-sourced. Prevents mislabelling construction materials (fabric,
    # interlining, thread) as TRIM_MASTER just because the LLM "matched" a name.
    def _is_master(v):   return bool(v) and "master" in str(v).lower()
    def _is_techpack(v): return bool(v) and ("tech pack" in str(v).lower() or "techpack" in str(v).lower())

    loc = item.get("_loc") or None
    master_ref = next((v for v in all_sources.values() if _is_master(v)), None)
    if not master_ref and loc and loc.get("sheet"):
        master_ref = f"Trim Master — {loc['sheet']}!{loc.get('cell', '')}"

    techpack_ref = next((v for v in all_sources.values() if _is_techpack(v)), None)
    if not techpack_ref and _is_techpack(item.get("source_ref")):
        techpack_ref = item.get("source_ref")
    if not techpack_ref and not master_ref:
        techpack_ref = item.get("source_ref") or "Tech Pack"
    buyer_rule   = None  # set later by BuyerRuleEngine

    # Conflicts → append to alerts; plus any explicit alerts the item carries
    # (e.g. BranchTrimResolver's "chọn theo số đo" measurement-condition flag).
    conflicts = item.get("conflicts") or []
    alerts = [f"CONFLICT: {c}" for c in conflicts if c]
    alerts += [a for a in (item.get("alerts") or []) if a]

    return TrimRow(
        category=category,
        sort_key=CATEGORY_ORDER.get(category, 99),
        material_name=name,
        material_code=_clean_material_code(item.get("material_code"), category),
        supplier=item.get("supplier") or None,
        supplier_code=item.get("supplier_code") or None,
        spec=item.get("spec") or None,
        placement=item.get("placement") or None,
        color=color_val,
        colors=colors,
        consumption=consumption,
        unit=unit,
        remark=item.get("remark") or None,
        source=TrimSource(
            techpack_ref=techpack_ref,
            master_ref=master_ref,
            buyer_rule=buyer_rule,
            email_ref=None,
            master_loc=loc,
        ),
        alerts=alerts,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

import re as _re

# Valid material code: contains digits + letters (like 220019916X, #FT770ES, GP21649C)
# Invalid: pure percentage text (C100%), plain 2-3 digit numbers, supplier names
_INVALID_CODE_RE = _re.compile(
    r"^C?\d+%"           # C100%, 100%
    r"|^\d{1,3}$"        # "602", "18" — too short, likely a size or count
    r"|^[A-Z]+\s"        # starts with word+space → probably supplier name
    r"|LF$",             # ends in bare "LF" — "UHZTGR00200 LF" keep, "LF" alone discard
    _re.IGNORECASE,
)


def _clean_material_code(raw: Any, category: str = "") -> Optional[str]:
    """Return None if raw looks like spec text, not an actual material code.

    Exception: thread ticket numbers ARE short numerics (602, 603) — for
    THREAD & BUTTON a bare 3-digit code is legitimate and must be kept."""
    if not raw:
        return None
    code = str(raw).strip()
    if not code:
        return None
    if category == "THREAD & BUTTON" and _re.fullmatch(r"\d{3}", code):
        return code
    if _INVALID_CODE_RE.match(code):
        return None
    # A code without a single digit ("& Tag Hook") is a name fragment, and a
    # multi-word cell with no code-shaped token ("26SS NEW QUALITY") is a remark
    # the LLM misplaced. Real codes survive: "220013824X (height 3.2cm)".
    if not _re.search(r"\d", code):
        return None
    if _re.search(r"\s", code) and not any(
        len(t) >= 6 and sum(ch.isdigit() for ch in t) >= 3
        for t in _re.findall(r"[A-Za-z0-9#.\-]+", code)
    ):
        return None
    return code


def _clean_category(raw: str) -> str:
    """Normalize category string to canonical form."""
    raw = raw.upper().strip()
    # Handle variations the LLM might produce
    aliases = {
        "FABRIC": "FABRIC/YARN",
        "YARN": "FABRIC/YARN",
        "FABRIC / YARN": "FABRIC/YARN",
        "THREAD": "THREAD & BUTTON",
        "BUTTON": "THREAD & BUTTON",
        "THREAD AND BUTTON": "THREAD & BUTTON",
        "THREAD & BUTTON": "THREAD & BUTTON",
        "THREAD&BUTTON": "THREAD & BUTTON",
        "TRIM": "OTHER",
        "ACCESSORY": "OTHER",
        "ACCESSORIES": "OTHER",
    }
    return aliases.get(raw, raw)


def _normalize_consumption(raw: Any) -> Optional[str]:
    """Normalize consumption string: '1.35 m' → '1.35 M', '2pcs' → '2 PCS'."""
    if not raw:
        return None
    import re
    s = str(raw).strip()
    # Reject N/A literals
    if s.upper() in ("N/A", "NA", "NULL", "NONE", "-", "N.A."):
        return None
    # Reject weave counts (160X136, 70X80) and fabric weights (90g, 160gsm)
    if re.search(r"\b\d{2,3}[Xx]\d{2,3}\b", s):
        return None
    if re.fullmatch(r"\d+\s*(?:g|gsm|g/m\d*)", s, re.IGNORECASE):
        return None
    # Reject SPI counts (13~14 SPI)
    if re.search(r"\d+\s*(?:~|to|-)\s*\d+\s*SPI", s, re.IGNORECASE):
        return None
    # Already formatted correctly
    m = re.search(r"([\d.,]+)\s*([a-zA-Z]+)", s)
    if m:
        qty  = m.group(1).replace(",", ".")
        unit = _UNIT_MAP.get(m.group(2).lower(), m.group(2).upper())
        return f"{qty} {unit}"
    # Just a number
    m2 = re.search(r"[\d.,]+", s)
    if m2:
        return m2.group().replace(",", ".")
    return None


def _pick_source(sources: Dict[str, str], priority_fields: List[str]) -> Optional[str]:
    """Pick the most relevant source citation from the sources dict."""
    for field in priority_fields:
        if sources.get(field):
            return sources[field]
    # Return any non-empty source
    for v in sources.values():
        if v:
            return v
    return None
