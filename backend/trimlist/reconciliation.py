"""
reconciliation.py — Phase 6.5: Reverse reconciliation against the raw-line list.

The anti-miss guarantee: every verbatim raw BOM line (from RawLineExtractor) must be
represented by a row in the final trimlist. This step walks each raw line and asks
"does it appear in the output?" — any raw line with no matching row is RECOVERED as a
row (flagged for review) instead of being silently dropped.

Fully deterministic (no LLM) — token-overlap matching on name + placement + code.
"""
import logging
import re
from typing import Any, Dict, List, Tuple

from backend.trimlist.raw_line_extractor import name_tokens
from backend.trimlist.traceability import TrimRow, TrimSource, CATEGORY_ORDER, classify_category

logger = logging.getLogger(__name__)

_COVER_THRESHOLD = 0.5   # a raw line is "covered" if ≥50% of its tokens match a row


def _row_sig(row: TrimRow) -> set:
    """Identifying tokens of a row — every field a raw line may carry, so a verbatim
    line (name + code + supplier + spec + placement + qty + remark) can match it."""
    colors = " ".join(str(v) for v in (row.colors or {}).values())
    parts = " ".join(str(p) for p in (
        row.material_name, row.placement or "", row.material_code or "",
        row.supplier or "", row.spec or "", row.consumption or "",
        row.remark or "", row.color or "", colors,
    ))
    return name_tokens(parts)


def _covered(raw_sig: set, row_sigs: List[set]) -> bool:
    if not raw_sig:
        return True  # nothing distinctive to match (generic/blank) → don't recover
    for rs in row_sigs:
        if rs and len(raw_sig & rs) / len(raw_sig) >= _COVER_THRESHOLD:
            return True
    return False


# Category / section-header labels — a raw line that IS one of these is a separator
# row, not a trim item.
_SECTION_HEADERS = {
    "FABRIC/YARN", "FABRIC", "YARN", "INTERLINING", "INTERLINNING",
    "THREAD & BUTTON", "THREAD &BUTTON", "THREAD", "LABEL", "LABEL & HANG TAGS",
    "LABEL & HANG TAG", "PACKING", "PACKING MATERIALS", "OTHER", "BOM", "TRIM", "TRIMS",
}


def _looks_like_trim(raw_line: str) -> bool:
    """True only if the line names a real trim/material. Filters out Tech Pack prose
    (fit comments like 'Must improve bulging button', evaluation notes, brand/date
    metadata), section headers, and stray colorway thread codes ('G#17848').

    Key: the item TYPE must sit at the HEAD of the line. A real trim starts with its
    kind ("THREAD …", "INTERLINING …", "PLASTIC COLLARBAND"); a comment starts with a
    verb/other ("Must improve …") and only mentions a trim word deeper in the sentence.
    So we classify the first two tokens only — not the whole line (which would match
    'button' inside 'bulgingbutton')."""
    name = _short_name(raw_line)
    if name.strip().upper() in _SECTION_HEADERS:
        return False
    if re.fullmatch(r"(?:[A-Z]\d\s+)?G#\d+", name.strip(), re.IGNORECASE):
        return False
    head = re.findall(r"[A-Za-z0-9/&]+", name)[:2]
    return any(classify_category(t) != "OTHER" for t in head)


def _short_name(raw_line: str) -> str:
    """A concise material name from a verbatim raw line (drop leading numbering,
    take the first segment before a big gap)."""
    s = re.sub(r"^\s*\d+[\.\)]\s*", "", raw_line).strip()
    s = re.split(r"\s{2,}|\s\|\s|\t", s)[0].strip()
    return s[:80] or raw_line[:80]


def _extract_code(raw_line: str) -> Tuple[str, int]:
    """First material-code-shaped token in a raw line: alphanumeric, ≥7 chars,
    ≥4 digits (222042553X, UHZTGR00200, GP21649C…). Returns (code, position)."""
    for m in re.finditer(r"[A-Za-z0-9]{7,}", raw_line):
        if sum(c.isdigit() for c in m.group()) >= 4:
            return m.group(), m.start()
    return "", -1


def _recovered_row(raw: str) -> TrimRow:
    """Build a usable row from a missed raw line — not just the line dumped as a
    name. The code token splits the line: name before it, and it IS the code."""
    code, pos = _extract_code(raw)
    name = raw[:pos].strip(" \t-–—&|") if pos > 0 else _short_name(raw)
    name = name or _short_name(raw)
    qty = re.search(r"\b(\d+)\s*(?:ea|pcs?|sets?)\b", raw, re.IGNORECASE)
    cat = classify_category(name) or "OTHER"
    return TrimRow(
        category=cat,
        sort_key=CATEGORY_ORDER.get(cat, 99),
        material_name=name[:80],
        material_code=code or None,
        consumption=f"{qty.group(1)} PCS" if qty else None,
        remark=raw[:160],
        source=TrimSource(techpack_ref="Raw BOM line (recovered)"),
        alerts=["WARNING: Recovered from raw BOM — dòng bị bỏ sót khi dựng bảng, cần kiểm tra"],
    )


def reconcile(rows: List[TrimRow], raw_lines: List[str]) -> Tuple[List[TrimRow], Dict[str, Any]]:
    """
    Ensure every raw line is represented. Missing lines are recovered as rows.

    Returns (rows_including_recovered, report).
    """
    if not raw_lines:
        return rows, {"raw_count": 0, "output_count": len(rows), "recovered": 0, "missing_lines": []}

    # Raw lines come from the TECH PACK, so only Tech-Pack-sourced rows may claim
    # to cover one. A master-added row must never mask a missed Tech Pack line —
    # that is exactly how a stale master hangtag hid the 26SS one.
    row_sigs = [_row_sig(r) for r in rows if r.source.techpack_ref]

    recovered: List[TrimRow] = []
    missing_lines: List[str] = []
    for raw in raw_lines:
        if _covered(name_tokens(raw), row_sigs):
            continue
        # Only recover lines that are actually a MATERIAL/TRIM. Tech Packs also carry
        # fit comments, sample-evaluation notes and metadata (BRAND, DESIGNER, dates…)
        # which classify as OTHER — never turn those into trimlist rows.
        if not _looks_like_trim(raw):
            continue
        missing_lines.append(raw)
        recovered.append(_recovered_row(raw))

    if recovered:
        logger.warning(f"Reconciliation: recovered {len(recovered)} raw line(s) missing from output")

    report = {
        "raw_count":     len(raw_lines),
        "output_count":  len(rows),
        "recovered":     len(recovered),
        "missing_lines": missing_lines[:50],
    }
    return rows + recovered, report


# ── Phase 5.55: deterministic code sweep ──────────────────────────────────────

_QTY_MARKER = re.compile(r"\b\d+\s*(?:ea|pcs?|sets?)\b", re.IGNORECASE)
# A code written in parentheses behind a hash — "(#FT770ES)", "(#M1316-ES)" — is an
# explicit material-code callout, so it needs no qty marker to be trusted. Tech Packs
# use it on spec pages, where the BOM row itself only says "Pls see T/P".
_HASH_CODE = re.compile(r"\(#\s*([A-Za-z0-9._-]{3,})\s*\)")


def sweep_hash_codes(rows: List[TrimRow], full_text: str) -> Tuple[List[TrimRow], List[str]]:
    """Recover materials whose code the BOM defers to the spec pages. The BOM says
    'Pls see T/P' and the real code sits elsewhere as '(#CODE)'; any such code no
    row carries is a material we failed to extract."""
    if not full_text:
        return rows, []

    known: set = set()
    for r in rows:
        blob = " ".join(str(x or "") for x in (r.material_code, r.supplier_code, r.spec))
        known |= {t.lower() for t in re.findall(r"[A-Za-z0-9._-]{3,}", blob)}

    recovered: Dict[str, TrimRow] = {}
    for line in full_text.splitlines():
        for m in _HASH_CODE.finditer(line):
            code = m.group(1)
            if code.lower() in known or code.lower() in recovered:
                continue
            name = line[:m.start()].strip(" \t-–—*&|") or _short_name(line)
            cat = classify_category(name) or "OTHER"
            recovered[code.lower()] = TrimRow(
                category=cat,
                sort_key=CATEGORY_ORDER.get(cat, 99),
                material_name=name[:80],
                material_code=code,
                remark=line.strip()[:160],
                source=TrimSource(techpack_ref="Tech Pack spec page (recovered)"),
                alerts=["WARNING: Mã lấy từ trang spec (BOM ghi 'Pls see T/P') — kiểm tra vị trí sử dụng"],
            )

    if recovered:
        logger.warning(f"sweep_hash_codes: recovered {len(recovered)} code(s): {sorted(recovered)}")
    return rows + list(recovered.values()), sorted(recovered)


def sweep_missing_codes(rows: List[TrimRow], bom_text: str) -> Tuple[List[TrimRow], List[str]]:
    """LLM-free anti-miss net: every material-code token in the BOM text must be
    accounted for by some output row. A code no row carries anywhere (code, name,
    spec, colors…) is a missed item — rebuild its row from the physical line that
    contains it. Only lines with a per-garment qty marker ('1ea', '2 PCS') qualify,
    which excludes headers, dates and fabric-colorway references."""
    if not bom_text:
        return rows, []

    known: set = set()
    for r in rows:
        colors = " ".join(str(v) for v in (r.colors or {}).values())
        blob = " ".join(str(x or "") for x in (
            r.material_code, r.supplier_code, r.material_name, r.spec, r.remark, colors,
        ))
        known |= _code_tokens(blob)

    recovered: Dict[str, TrimRow] = {}
    for line in bom_text.splitlines():
        line = line.strip()
        if not line or not _QTY_MARKER.search(line):
            continue
        for code in _code_tokens(line):
            if code in known or code in recovered:
                continue
            row = _recovered_row(line)
            m = re.search(re.escape(code), line, re.IGNORECASE)
            row.material_code = m.group() if m else code
            row.alerts = ["WARNING: Mã có trong Tech Pack nhưng không dòng nào mang nó — đã dựng lại, cần kiểm tra"]
            recovered[code] = row

    if recovered:
        logger.warning(f"sweep_missing_codes: recovered {len(recovered)} code(s): {sorted(recovered)}")
    return rows + list(recovered.values()), sorted(recovered)


# ── Phase 5.6: cross-source dedup ─────────────────────────────────────────────

def _code_tokens(v: str) -> set:
    """Code-shaped tokens of a code cell (a master cell may stack several)."""
    return {
        t.lower() for t in re.findall(r"[A-Za-z0-9]{7,}", str(v or ""))
        if sum(c.isdigit() for c in t) >= 4
    }


def _tier(row: TrimRow) -> int:
    """0 = Tech Pack row, 1 = recovered raw line, 2 = master-only. Lower wins."""
    tp = row.source.techpack_ref or ""
    if tp and "recovered" not in tp.lower():
        return 0
    if tp:
        return 1
    return 2


def _same_item(a: TrimRow, b: TrimRow) -> bool:
    """Same physical item? When BOTH rows carry codes, the codes alone decide —
    disjoint codes mean different items no matter how similar the names ('Price
    tag sticker' must not swallow the hangtag). Only when a code is missing do
    names decide: overlap ≥60% from either side. Category is deliberately
    ignored — the two sources classify differently."""
    ca, cb = _code_tokens(a.material_code or ""), _code_tokens(b.material_code or "")
    if ca and cb:
        return bool(ca & cb)
    ta, tb = name_tokens(a.material_name), name_tokens(b.material_name)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter / len(ta) >= 0.6 or inter / len(tb) >= 0.6


# Deliberately NOT remark/placement: a master variant row's remark ("CLASSIC FIT…")
# on a Tech Pack row for a different variant misleads more than an empty cell.
_ENRICH_FIELDS = ("material_code", "supplier", "consumption")


def _same_item_strict(a: TrimRow, b: TrimRow) -> bool:
    """Same-tier duplicate: identical code AND same name AND same placement (or one
    blank). Strict on purpose — the SAME code on DIFFERENT placements is a real
    repeat (one interlining used in 2 places), never a duplicate."""
    ca, cb = _code_tokens(a.material_code or ""), _code_tokens(b.material_code or "")
    if not ca or not cb or not (ca & cb):
        return False
    ta, tb = name_tokens(a.material_name), name_tokens(b.material_name)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    if inter / len(ta) < 0.6 or inter / len(tb) < 0.6:
        return False
    pa = (a.placement or "").strip().lower()
    pb = (b.placement or "").strip().lower()
    return pa == pb or not pa or not pb


def dedup_cross_source(rows: List[TrimRow]) -> Tuple[List[TrimRow], int]:
    """Drop rows that duplicate the same item, keeping the most trustworthy one
    (Tech Pack > recovered > master) and pulling any field the kept row lacks from
    the dropped one. Across tiers a code/name match is enough; within one tier
    only the strict rule applies — a Tech Pack legitimately repeats THREAD /
    INTERLINING per placement."""
    kept: List[TrimRow] = []
    dropped = 0
    for row in sorted(rows, key=_tier):
        winner = next(
            (k for k in kept
             if (_tier(k) != _tier(row) and _same_item(k, row))
             or (_tier(k) == _tier(row) and _same_item_strict(k, row))),
            None,
        )
        if winner is None:
            kept.append(row)
            continue
        dropped += 1
        for f in _ENRICH_FIELDS:
            if not getattr(winner, f, None) and getattr(row, f, None):
                setattr(winner, f, getattr(row, f))
        src = row.source.master_ref or row.source.techpack_ref or "nguồn khác"
        winner.alerts = (winner.alerts or []) + [
            f"INFO: Đã gộp dòng trùng từ {src}"
        ]
    if dropped:
        logger.info(f"dedup_cross_source: dropped {dropped} duplicate row(s)")
    return kept, dropped
