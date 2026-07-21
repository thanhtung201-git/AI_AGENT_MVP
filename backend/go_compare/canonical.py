"""
canonical.py — The single canonical schema both PO and GO map into.

Design goals:
  - Layout-independent: no assumptions about where fields appear
  - Traceable: every value carries a Source (document / sheet / cell) + confidence
  - Comparable: PO and GO become the same shape so comparison is business-meaning,
    not Excel-coordinate, based.

Nothing here is customer-specific. Field names are generic garment-order concepts.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ── Traceability ──────────────────────────────────────────────────────────────

@dataclass
class Source:
    """Where a value came from — used for the 'Source' + 'Confidence' report columns."""
    document: str = ""          # e.g. "PO" | "GO Information"
    sheet: str = ""             # e.g. "HZ" | "Header + main+Color + Size"
    cell: str = ""              # e.g. "D25" (best-effort from LLM; may be a region)
    confidence: str = "medium"  # "high" | "medium" | "low"

    def label(self) -> str:
        parts = [p for p in (self.document, self.sheet, self.cell) if p]
        return " · ".join(parts) if parts else "—"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FieldValue:
    """A value + its provenance. Used for header-level scalar fields."""
    value: Any = None
    source: Source = field(default_factory=Source)

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "source": self.source.to_dict()}


# ── Order line ────────────────────────────────────────────────────────────────

@dataclass
class OrderLine:
    """
    One order line = one (style × color × size) demand, or an aggregate when the
    document is less granular. size_breakdown holds per-size quantities when present.
    """
    style: str = ""
    block: int = 0                                   # 1-based run of this style in the doc
    color_code: str = ""
    color_name: str = ""
    size: str = ""                                   # single size, if line is per-size
    size_breakdown: Dict[str, float] = field(default_factory=dict)  # {"00S": 175, ...}
    qty: float = 0.0                                 # total qty for this line
    order_date: str = ""                             # buyer PO / order-placement date
    delivery_date: str = ""
    destination: str = ""                            # region/market if the doc splits it
    source: Source = field(default_factory=Source)

    def key(self) -> tuple:
        """Business identity for matching PO↔GO lines (layout-independent)."""
        return (
            _norm(self.style),
            _norm(self.color_code) or _norm(self.color_name),
            _norm(self.size),
            _norm(self.destination),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source"] = self.source.to_dict()
        return d


# ── Canonical order (top-level) ───────────────────────────────────────────────

@dataclass
class CanonicalOrder:
    """Unified representation of a PO or a GO. Both map into this."""
    document_type: str = ""      # "PO" | "GO"
    po_number: FieldValue = field(default_factory=FieldValue)
    go_number: FieldValue = field(default_factory=FieldValue)
    buyer: FieldValue = field(default_factory=FieldValue)
    style: FieldValue = field(default_factory=FieldValue)
    season: FieldValue = field(default_factory=FieldValue)
    factory: FieldValue = field(default_factory=FieldValue)
    order_date: FieldValue = field(default_factory=FieldValue)     # buyer PO / order date
    delivery_date: FieldValue = field(default_factory=FieldValue)
    lines: List[OrderLine] = field(default_factory=list)

    # ── Derived aggregates (deterministic, not from LLM) ──────────────────────
    def total_qty(self) -> float:
        return sum(l.qty for l in self.lines)

    def colors(self) -> List[str]:
        seen, out = set(), []
        for l in self.lines:
            c = _norm(l.color_code) or _norm(l.color_name)
            if c and c not in seen:
                seen.add(c)
                out.append(l.color_code or l.color_name)
        return out

    def sizes(self) -> List[str]:
        seen, out = set(), []
        for l in self.lines:
            for s in ([l.size] if l.size else list(l.size_breakdown.keys())):
                sn = _norm(s)
                if sn and sn not in seen:
                    seen.add(sn)
                    out.append(s)
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type,
            "po_number":     self.po_number.to_dict(),
            "go_number":     self.go_number.to_dict(),
            "buyer":         self.buyer.to_dict(),
            "style":         self.style.to_dict(),
            "season":        self.season.to_dict(),
            "factory":       self.factory.to_dict(),
            "order_date":    self.order_date.to_dict(),
            "delivery_date": self.delivery_date.to_dict(),
            "lines":         [l.to_dict() for l in self.lines],
            "total_qty":     self.total_qty(),
        }


# ── Builders from LLM JSON ────────────────────────────────────────────────────

def field_from_llm(obj: Any, document: str) -> FieldValue:
    """
    Accepts either a bare scalar or {"value":..., "source":{...}} from the LLM
    and returns a FieldValue. Layout-agnostic.
    """
    # LLM sometimes returns a LIST of {value, source} for a field (e.g. multi-style
    # documents). Collapse to the first entry, but keep all distinct values joined
    # so nothing is silently dropped.
    if isinstance(obj, list):
        entries = [field_from_llm(o, document) for o in obj]
        entries = [e for e in entries if e.value not in (None, "")]
        if not entries:
            return FieldValue(value=None, source=Source(document=document, confidence="low"))
        distinct = []
        for e in entries:
            if e.value not in distinct:
                distinct.append(e.value)
        first = entries[0]
        first.value = distinct[0] if len(distinct) == 1 else " / ".join(str(v) for v in distinct)
        return first

    if isinstance(obj, dict) and "value" in obj:
        src = obj.get("source") or {}
        return FieldValue(
            value=_clean_scalar(obj.get("value")),
            source=Source(
                document=document,
                sheet=str(src.get("sheet") or ""),
                cell=str(src.get("cell") or ""),
                confidence=str(src.get("confidence") or "medium"),
            ),
        )
    return FieldValue(value=_clean_scalar(obj), source=Source(document=document, confidence="low"))


def order_from_llm(data: Dict[str, Any], document_type: str, document_label: str) -> CanonicalOrder:
    """Build a CanonicalOrder from the LLM's JSON output."""
    order = CanonicalOrder(document_type=document_type)
    order.po_number     = field_from_llm(data.get("po_number"),     document_label)
    order.go_number     = field_from_llm(data.get("go_number"),     document_label)
    order.buyer         = field_from_llm(data.get("buyer"),         document_label)
    order.style         = field_from_llm(data.get("style"),         document_label)
    order.season        = field_from_llm(data.get("season"),        document_label)
    order.factory       = field_from_llm(data.get("factory"),       document_label)
    order.order_date    = field_from_llm(data.get("order_date"),    document_label)
    order.delivery_date = field_from_llm(data.get("delivery_date"), document_label)

    for raw in (data.get("lines") or data.get("orders") or []):
        if not isinstance(raw, dict):
            continue
        src = raw.get("source") or {}
        sb  = raw.get("size_breakdown") or {}
        clean_sb = {}
        if isinstance(sb, dict):
            for k, v in sb.items():
                num = _to_number(v)
                if num is not None and str(k).strip():
                    clean_sb[str(k).strip()] = num
        line = OrderLine(
            style=str(raw.get("style") or data.get("style_value") or "").strip(),
            color_code=str(raw.get("color_code") or raw.get("color") or "").strip(),
            color_name=str(raw.get("color_name") or "").strip(),
            size=str(raw.get("size") or "").strip(),
            size_breakdown=clean_sb,
            qty=_to_number(raw.get("qty")) or (sum(clean_sb.values()) if clean_sb else 0.0),
            order_date=str(raw.get("order_date") or "").strip(),
            delivery_date=str(raw.get("delivery_date") or "").strip(),
            destination=str(raw.get("destination") or raw.get("market") or "").strip(),
            source=Source(
                document=document_label,
                sheet=str(src.get("sheet") or ""),
                cell=str(src.get("cell") or ""),
                confidence=str(src.get("confidence") or "medium"),
            ),
        )
        order.lines.append(line)

    _forward_fill_style(order)
    return order


def _looks_like_style(s: str) -> bool:
    """
    Generic signal that a token is a product/article code rather than an
    order-type marker: it mixes letters and digits and is reasonably long.
    Works across brands (HZSH6F201, ABC-1234, 26FW-001…). Order-type tokens like
    "01", "STOCK", "SMS", "BULK", "TTL" fail this test.
    """
    t = str(s or "").strip()
    if len(t) < 4:
        return False
    has_alpha = any(c.isalpha() for c in t)
    has_digit = any(c.isdigit() for c in t)
    return has_alpha and has_digit


def _forward_fill_style(order: CanonicalOrder) -> None:
    """
    Carry the last valid block-header style down to lines whose style is empty or
    is an order-type marker (not an article code). Sequential inheritance only —
    no assumptions about which column/row the style lives in.

    Safe fallback: if NO line has an article-code-shaped style (e.g. a brand that
    uses purely numeric styles), nothing is overridden.
    """
    last_valid = ""
    # Seed from the header-level style only if it is a SINGLE article-code token
    # (multi-style headers get joined with " / " and must not seed the fill).
    header_style = str(order.style.value or "").strip()
    if _looks_like_style(header_style) and " " not in header_style and "/" not in header_style:
        last_valid = header_style

    for line in order.lines:
        cur = (line.style or "").strip()
        if _looks_like_style(cur):
            last_valid = cur
        elif last_valid:
            line.style = last_valid


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _clean_scalar(v: Any) -> Any:
    if isinstance(v, str):
        s = v.strip()
        return s if s.lower() not in ("", "n/a", "na", "null", "none", "-") else None
    return v


def _to_number(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None
