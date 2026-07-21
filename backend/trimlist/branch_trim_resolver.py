"""
branch_trim_resolver.py — Phase 3.5 (deterministic replacement for PackingAutoIncluder).

Ana's step 3: take the branch's Trim Master list and add the packing/label items the
Tech Pack doesn't carry — but respecting the branch's own conditions.

Deterministic, NO LLM guessing:
  - Take EVERY base-sheet item of the branch (completeness).
  - Style exceptions (from the branch's exception sheet): if the current style is
    listed, drop the items the reminder names (e.g. "no Shirt Board / Butterfly").
  - Measurement-conditional rows (REMARK like "Collar Height @ CB 4.2cm"): keep them
    but FLAG "chọn theo số đo" — we never silently pick/drop a measured variant.
  - Dedup against Tech Pack by a FIXED key: material CODE first, else category +
    name tokens. No natural-language "are these the same" call.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from backend.trimlist.raw_line_extractor import name_tokens
from backend.trimlist.traceability import classify_category

logger = logging.getLogger(__name__)

_DUP_THRESHOLD = 0.6


def _norm_code(v: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower())


def _season_tokens(s: str) -> set:
    """Canonical season tokens of a string: '26SS', 'SS26', 'From SS26…' → {'ss26'}."""
    low = (s or "").lower()
    out = {f"{a}{b}" for a, b in re.findall(r"\b(ss|fw)\s*(\d{2})\b", low)}
    out |= {f"{a}{b}" for b, a in re.findall(r"\b(\d{2})\s*(ss|fw)\b", low)}
    return out


def _line_code(line: str) -> str:
    m = re.search(r"[A-Za-z0-9]{7,}", line)
    return m.group() if m else ""


def _select_code_version(
    code_cell: str, remark: str, season: str, techpack_text: str = ""
) -> Tuple[str, Optional[str]]:
    """A master code cell may stack one code PER SEASON ('222026720X(...)\\n…\\n
    222042553X(from SS26 balanced order)'). Pick the right line for THIS order:
    first by hard evidence — exactly one of the stacked codes appears in the Tech
    Pack itself — then by the season qualifier in the cell or its paired remark
    line. Returns (code, alert|None); keeps the full cell + a warning when
    genuinely ambiguous."""
    lines = [l.strip() for l in str(code_cell or "").splitlines() if l.strip()]
    if len(lines) <= 1:
        return code_cell, None

    if techpack_text:
        low = techpack_text.lower()
        hits = [l for l in lines if _line_code(l) and _line_code(l).lower() in low]
        if len(hits) == 1:
            code = _line_code(hits[0])
            return code, f"INFO: Chọn mã '{code}' — chính Tech Pack dùng mã này ({len(lines)} phiên bản trong master)"

    want = _season_tokens(season)
    if want:
        remarks = [l.strip() for l in str(remark or "").splitlines() if l.strip()]
        paired = remarks if len(remarks) == len(lines) else [""] * len(lines)
        hits = [l for l, r in zip(lines, paired) if _season_tokens(l + " " + r) & want]
        if len(hits) == 1:
            code = _line_code(hits[0]) or hits[0]
            return code, f"INFO: Chọn mã '{code}' theo mùa {season} trong {len(lines)} phiên bản"
    return code_cell, (
        f"WARNING: Ô mã có {len(lines)} phiên bản theo mùa — cần chọn đúng phiên bản cho đơn này"
    )


def resolve_code_versions(rows, season: str, techpack_text: str) -> int:
    """Late pass over final TrimRows: any code cell still stacking several
    versioned codes gets the same selection, no matter which path (LLM merge,
    branch add, enrich) produced the row. Returns how many rows were resolved."""
    n = 0
    for row in rows:
        cell = row.material_code or ""
        if "\n" not in cell:
            continue
        code, alert = _select_code_version(cell, row.remark or "", season, techpack_text)
        if code != cell:
            row.material_code = code
            n += 1
        if alert:
            row.alerts = (row.alerts or []) + [alert]
    return n


# A REMARK that opens with one of these states WHEN the row applies, rather than
# describing it. "For garment dye order…", "Fabric with Anti-Bacterial finishing…"
_COND_PREFIX = re.compile(r"^\s*(for|fabric with|only for|apply to|applies to)\b", re.IGNORECASE)
# Words that carry no discriminating power inside such a clause.
_COND_STOP = {
    "for", "with", "fabric", "style", "styles", "order", "orders", "only", "apply",
    "applies", "and", "the", "all", "put", "use", "used", "both", "each", "from",
}


def _row_condition(remark: str) -> Optional[str]:
    """The condition this master row is gated on, if its REMARK states one.

    A packing master lists every row the BRANCH may ever need; the REMARK says which
    orders actually need it ("For garment dye order…", "Fabric with Anti-Bacterial
    finishing…"). We surface that condition on the row instead of guessing whether
    this order meets it: deciding needs judgement about the garment (is this a
    garment-dye order?) that neither a keyword test nor an 8B model gets right, and
    dropping a trim the order does need stops production. Returns the clause, else
    None. Measurement conditions pick a VARIANT and are flagged separately.
    """
    if not remark:
        return None
    first = remark.strip().splitlines()[0]
    if not _COND_PREFIX.match(first):
        return None
    clause = re.split(r"[,;]", first)[0].strip()
    if _is_measurement_conditional(clause):
        return None
    if not ({t for t in re.findall(r"[a-z]{3,}", clause.lower())} - _COND_STOP):
        return None
    return clause


def _is_measurement_conditional(remark: str) -> bool:
    """REMARK carries a measurement condition (e.g. 'For Collar Height @ CB 4.2cm')."""
    if not remark:
        return False
    r = remark.lower()
    return bool(re.search(r"\d+(\.\d+)?\s*(cm|mm)", r)) and \
        bool(re.search(r"height|collar|neck|band|@\s*cb|placket", r))


class BranchTrimResolver:
    """Deterministically resolve the branch packing/label items to add."""

    def resolve(
        self,
        master_items: List[Dict],
        exceptions: Dict[str, List[str]],
        techpack_items: List[Dict],
        style_code: str = "",
        season: str = "",
    ) -> Dict[str, Any]:
        """
        Returns {"items": [...to add...], "report": {...}}.
        """
        if not master_items:
            return {"items": [], "report": {"added": 0, "excluded_by_style": 0,
                                            "flagged_conditional": 0, "deduped": 0}}

        excluded_names = self._excluded_item_names(exceptions, style_code)

        # Pre-index Tech Pack for dedup
        tp_codes = {_norm_code(t.get("material_code")) for t in techpack_items if t.get("material_code")}
        tp_by_cat: Dict[str, List[set]] = {}
        for t in techpack_items:
            cat = (t.get("category") or classify_category(t.get("material_name", ""))).upper()
            tp_by_cat.setdefault(cat, []).append(name_tokens(t.get("material_name", "")))

        added, deduped, excluded, flagged, conditional = [], 0, 0, 0, 0
        for m in master_items:
            name = (m.get("trim_item") or "").strip()
            if not name:
                continue

            # 1. Style exception
            if self._matches_excluded(name, excluded_names):
                excluded += 1
                continue

            # 2. Dedup vs Tech Pack (fixed key: code, then category + name tokens)
            if self._is_duplicate(m, name, tp_codes, tp_by_cat):
                deduped += 1
                continue

            cat  = classify_category(name) or "OTHER"
            code = (m.get("supplier_code") or "").strip()
            qty  = m.get("qty_per_garment")
            unit = (m.get("unit") or "").strip()
            consumption = f"{qty:g} {unit}".strip() if qty else (unit or None)
            remark = (m.get("remark") or "").strip() or None

            alerts: List[str] = []
            code, season_alert = _select_code_version(code, remark or "", season)
            if season_alert:
                alerts.append(season_alert)
            if _is_measurement_conditional(remark or ""):
                flagged += 1
                alerts.append("WARNING: Dòng có điều kiện theo số đo — chọn biến thể đúng theo Tech Pack")
            cond = _row_condition(remark or "")
            if cond:
                conditional += 1
                alerts.append(
                    f"WARNING: Chỉ dùng khi '{cond}' — Tech Pack không nêu điều kiện này. "
                    f"Bỏ dòng nếu đơn không thuộc diện đó"
                )

            loc     = m.get("_loc") or {}
            loc_txt = (f"{loc.get('sheet')}!{loc.get('cell')}"
                       if loc.get("sheet") and loc.get("cell") else (loc.get("sheet") or "branch list"))
            added.append({
                "material_name": name,
                "material_code": code or None,
                "supplier":      (m.get("supplier") or "").strip() or None,
                "category":      cat if cat in ("PACKING", "LABEL") else "PACKING",
                "consumption":   consumption,
                "remark":        remark,
                "source_ref":    f"Trim Master — {loc_txt}",
                "sources":       {"material_code": f"Trim Master — {loc_txt}"} if code else {},
                "conflicts":     [],
                "confidence":    "master_branch",
                "master_match":  name,
                "alerts":        alerts,
                "_loc":          loc or None,
            })

        report = {"added": len(added), "excluded_by_style": excluded,
                  "flagged_conditional": flagged, "flagged_rule": conditional,
                  "deduped": deduped}
        logger.info(f"BranchTrimResolver: {report}")
        return {"items": added, "report": report}

    # ── helpers ───────────────────────────────────────────────────────────────

    def _excluded_item_names(self, exceptions: Dict[str, List[str]], style_code: str) -> List[set]:
        """If the current style is in the exception list, the reminder names which
        items to drop. Return their token sets (empty → nothing excluded)."""
        styles = exceptions.get("styles") or []
        if not style_code or not styles:
            return []
        sc = _norm_code(style_code)
        if not any(sc == _norm_code(s) or sc in _norm_code(s) or _norm_code(s) in sc for s in styles):
            return []
        # Pull candidate item names from the reminders (uppercase item-ish phrases).
        excluded: List[set] = []
        for rem in exceptions.get("reminders") or []:
            for m in re.findall(r"\b([A-Z][A-Z /]{3,})\b", rem):
                toks = name_tokens(m)
                if toks:
                    excluded.append(toks)
        return excluded

    @staticmethod
    def _matches_excluded(name: str, excluded_names: List[set]) -> bool:
        nt = name_tokens(name)
        if not nt:
            return False
        for ex in excluded_names:
            if ex and len(nt & ex) / len(ex) >= 0.6:
                return True
        return False

    @staticmethod
    def _is_duplicate(m: Dict, name: str, tp_codes: set, tp_by_cat: Dict[str, List[set]]) -> bool:
        code = _norm_code(m.get("supplier_code"))
        if code and code in tp_codes:
            return True
        cat = (classify_category(name) or "OTHER").upper()
        nt  = name_tokens(name)
        if not nt:
            return False
        for tset in tp_by_cat.get(cat, []):
            if tset and len(nt & tset) / len(nt) >= _DUP_THRESHOLD:
                return True
        return False
