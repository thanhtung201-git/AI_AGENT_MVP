"""
compare_engine.py — Compare a PO CanonicalOrder against a GO CanonicalOrder by
BUSINESS MEANING, not Excel coordinates.

Deterministic Python (no LLM): matching is done on each line's business key
(style × color × size × destination), so it works regardless of how either
document was laid out.

Detects:
  - Missing rows (in PO, absent from GO)
  - Extra rows (in GO, absent from PO)
  - Quantity mismatch
  - Size mismatch / Color mismatch (surfaced as missing/extra keys)
  - Delivery mismatch
  - Style mismatch / Buyer mismatch (header level)

Output:
  rows   : list of CompareRow (feeds Compare_Report.xlsx)
  alerts : list of Alert dicts (feeds Alerts.json)
"""
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from backend.go_compare.canonical import CanonicalOrder, OrderLine, FieldValue

logger = logging.getLogger(__name__)

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"


@dataclass
class CompareRow:
    """One line of the Compare_Report — mirrors the required output columns."""
    field: str                 # what is being compared (e.g. "Qty · N2 · 00S")
    status: str                # "MATCH" | "MISMATCH" | "MISSING" | "EXTRA"
    po_value: str
    go_value: str
    difference: str
    source: str                # traceability label
    confidence: str            # high/medium/low

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Alert:
    level: str
    category: str
    message: str
    po_value: Optional[str] = None
    go_value: Optional[str] = None
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CompareEngine:
    """Compares two canonical orders and produces report rows + alerts."""

    def __init__(self, qty_tolerance_pct: float = 0.0):
        # tolerance is configurable, not hardcoded per customer
        self.qty_tol = qty_tolerance_pct

    def compare(self, po: CanonicalOrder, go: CanonicalOrder) -> Dict[str, Any]:
        rows: List[CompareRow] = []
        alerts: List[Alert] = []

        self._compare_header(po, go, rows, alerts)
        self._compare_lines(po, go, rows, alerts)

        summary = self._summarize(rows, alerts, po, go)
        return {
            "rows":    [r.to_dict() for r in rows],
            "alerts":  [a.to_dict() for a in alerts],
            "summary": summary,
        }

    # ── Header-level ──────────────────────────────────────────────────────────

    def _compare_header(self, po, go, rows, alerts):
        pairs = [
            ("Buyer",         po.buyer,         go.buyer,         WARNING),
            ("Style",         po.style,         go.style,         WARNING),
            ("Season",        po.season,        go.season,        INFO),
            ("Delivery Date", po.delivery_date, go.delivery_date, WARNING),
            ("PO Number",     po.po_number,     go.po_number,     INFO),
        ]
        for name, pf, gf, level in pairs:
            pv, gv = _s(pf.value), _s(gf.value)
            if not pv and not gv:
                continue
            match = _norm(pv) == _norm(gv) and pv != ""
            status = "MATCH" if match else ("MISSING" if not gv else "MISMATCH")
            rows.append(CompareRow(
                field=name,
                status=status,
                po_value=pv or "—",
                go_value=gv or "—",
                difference="" if match else "changed",
                source=f"{pf.source.label()}  →  {gf.source.label()}",
                confidence=_min_conf(pf.source.confidence, gf.source.confidence),
            ))
            if not match and pv and gv:
                alerts.append(Alert(level, f"{name.lower()}_mismatch",
                                    f"{name} mismatch: PO='{pv}' vs GO='{gv}'",
                                    po_value=pv, go_value=gv,
                                    source=gf.source.label()))

        # Total quantity
        po_t, go_t = po.total_qty(), go.total_qty()
        diff = go_t - po_t
        tol  = abs(po_t) * self.qty_tol
        match = abs(diff) <= tol
        rows.append(CompareRow(
            field="Total Quantity",
            status="MATCH" if match else "MISMATCH",
            po_value=f"{po_t:,.0f}",
            go_value=f"{go_t:,.0f}",
            difference="" if match else f"{diff:+,.0f}",
            source="derived (sum of lines)",
            confidence="high",
        ))
        if not match:
            pct = abs(diff) / po_t * 100 if po_t else 100
            alerts.append(Alert(
                ERROR if pct > 5 else WARNING, "quantity_mismatch",
                f"Total quantity mismatch: PO={po_t:,.0f} vs GO={go_t:,.0f} ({diff:+,.0f})",
                po_value=f"{po_t:,.0f}", go_value=f"{go_t:,.0f}",
            ))

    # ── Line-level (business-key matching) ────────────────────────────────────

    def _compare_lines(self, po, go, rows, alerts):
        po_idx = _index_lines(po.lines)
        go_idx = _index_lines(go.lines)
        all_keys = list(po_idx.keys()) + [k for k in go_idx if k not in po_idx]

        for key in all_keys:
            pl = po_idx.get(key)
            gl = go_idx.get(key)
            label = _key_label(key)

            if pl and not gl:
                rows.append(CompareRow(
                    field=f"Line · {label}", status="MISSING",
                    po_value=f"{pl.qty:,.0f}", go_value="—",
                    difference=f"-{pl.qty:,.0f}",
                    source=pl.source.label(), confidence=pl.source.confidence,
                ))
                alerts.append(Alert(ERROR, "missing_row",
                                    f"Line present in PO but missing in GO: {label} (qty {pl.qty:,.0f})",
                                    po_value=f"{pl.qty:,.0f}", source=pl.source.label()))
                continue

            if gl and not pl:
                rows.append(CompareRow(
                    field=f"Line · {label}", status="EXTRA",
                    po_value="—", go_value=f"{gl.qty:,.0f}",
                    difference=f"+{gl.qty:,.0f}",
                    source=gl.source.label(), confidence=gl.source.confidence,
                ))
                alerts.append(Alert(INFO, "extra_row",
                                    f"Line present in GO but not in PO: {label} (qty {gl.qty:,.0f})",
                                    go_value=f"{gl.qty:,.0f}", source=gl.source.label()))
                continue

            # both present — compare qty and delivery
            diff = gl.qty - pl.qty
            tol  = abs(pl.qty) * self.qty_tol
            qmatch = abs(diff) <= tol
            rows.append(CompareRow(
                field=f"Qty · {label}",
                status="MATCH" if qmatch else "MISMATCH",
                po_value=f"{pl.qty:,.0f}", go_value=f"{gl.qty:,.0f}",
                difference="" if qmatch else f"{diff:+,.0f}",
                source=f"{pl.source.label()} → {gl.source.label()}",
                confidence=_min_conf(pl.source.confidence, gl.source.confidence),
            ))
            if not qmatch:
                pct = abs(diff) / pl.qty * 100 if pl.qty else 100
                alerts.append(Alert(
                    ERROR if pct > 5 else WARNING, "quantity_mismatch",
                    f"Qty mismatch {label}: PO={pl.qty:,.0f} vs GO={gl.qty:,.0f} ({diff:+,.0f})",
                    po_value=f"{pl.qty:,.0f}", go_value=f"{gl.qty:,.0f}",
                    source=gl.source.label()))

            # delivery date at line level
            if _norm(pl.delivery_date) and _norm(gl.delivery_date) and \
               _norm(pl.delivery_date) != _norm(gl.delivery_date):
                alerts.append(Alert(WARNING, "delivery_mismatch",
                                    f"Delivery mismatch {label}: PO='{pl.delivery_date}' vs GO='{gl.delivery_date}'",
                                    po_value=pl.delivery_date, go_value=gl.delivery_date))

    # ── Summary ───────────────────────────────────────────────────────────────

    def _summarize(self, rows, alerts, po, go) -> Dict[str, Any]:
        n_err  = sum(1 for a in alerts if a.level == ERROR)
        n_warn = sum(1 for a in alerts if a.level == WARNING)
        n_info = sum(1 for a in alerts if a.level == INFO)
        if n_err:
            status = "MISMATCH"
        elif n_warn:
            status = "PARTIAL"
        else:
            status = "OK"
        return {
            "status":     status,
            "errors":     n_err,
            "warnings":   n_warn,
            "infos":      n_info,
            "po_total":   po.total_qty(),
            "go_total":   go.total_qty(),
            "qty_diff":   go.total_qty() - po.total_qty(),
            "po_lines":   len(po.lines),
            "go_lines":   len(go.lines),
            "compared":   len(rows),
        }


# ── helpers ───────────────────────────────────────────────────────────────────

def _index_lines(lines: List[OrderLine]) -> Dict[tuple, OrderLine]:
    """Index lines by business key, merging duplicates by summing qty."""
    idx: Dict[tuple, OrderLine] = {}
    for l in lines:
        k = l.key()
        if k in idx:
            idx[k].qty += l.qty
            for s, v in l.size_breakdown.items():
                idx[k].size_breakdown[s] = idx[k].size_breakdown.get(s, 0) + v
        else:
            # shallow copy so we don't mutate the source order
            idx[k] = OrderLine(
                style=l.style, color_code=l.color_code, color_name=l.color_name,
                size=l.size, size_breakdown=dict(l.size_breakdown), qty=l.qty,
                delivery_date=l.delivery_date, destination=l.destination, source=l.source,
            )
    return idx


def _key_label(key: tuple) -> str:
    style, color, size, dest = key
    parts = [p for p in (style, color, size, dest) if p]
    return " · ".join(parts) if parts else "(line)"


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _norm(v: Any) -> str:
    return _s(v).lower()


def _min_conf(a: str, b: str) -> str:
    order = {"high": 3, "medium": 2, "low": 1}
    return a if order.get(a, 2) <= order.get(b, 2) else b
