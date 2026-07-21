"""
Unit tests for the deterministic structure-based PO parser.

Runs with pytest OR standalone:  python backend/go_compare/tests/test_po_parser.py

Each test builds a synthetic PO grid (no real file, no customer data) to prove the
parser generalizes across layouts: multiple styles/colors, blank rows, shifted
columns, different size sets, extra notes, and to prove correctness of color totals
(sum of sizes, never the TTL column) and absence of state leakage.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from backend.go_compare.po_parser.grid import GridSheet
from backend.go_compare.po_parser.parser import POParser
from backend.go_compare.po_parser.validator import POValidator
from backend.go_compare.canonical import CanonicalOrder, OrderLine


# ── grid builders ─────────────────────────────────────────────────────────────

def _basic_grid(lead_blank_cols: int = 0, blank_rows: bool = False):
    """
    Layout: [Style, Color, TTL(subtotal), S, M, L]
    Two styles, different colors. TTL column deliberately WRONG to prove the parser
    computes color totals from the sizes, not the TTL column.
    """
    pad = [None] * lead_blank_cols
    rows = [
        pad + [None,     None,  "TTL", None, None, None],   # group header
        pad + [None,     None,  None,  "S",  "M",  "L"],    # size header
        pad + ["ST-001", "TTL", 999,   30,   40,   50],     # style hdr (TTL wrong)
        pad + [None,     "RED",  999,   10,   20,   30],     # color (sum=60, TTL wrong)
        pad + [None,     "BLU",  999,   5,    5,    5],      # color (sum=15)
        pad + ["ST-002", "TTL", 0,     1,    1,    1],       # new style hdr
        pad + [None,     "GRN",  0,     7,    8,    9],      # color (sum=24)
    ]
    if blank_rows:
        out = []
        for r in rows:
            out.append(r)
            out.append([None] * len(r))   # inject blank row after each
        rows = out
    return GridSheet.from_matrix("Sheet1", rows)


def _order(grid):
    return POParser().parse_sheet(grid)


# ── tests ─────────────────────────────────────────────────────────────────────

def test_multiple_styles_and_colors():
    o = _order(_basic_grid())
    styles = {l.style for l in o.lines}
    assert styles == {"ST-001", "ST-002"}, styles
    assert len(o.lines) == 3
    reds = [l for l in o.lines if l.color_code == "RED"]
    assert reds and reds[0].style == "ST-001"


def test_color_total_is_sum_not_ttl():
    """Color total MUST equal the sum of sizes, never the (wrong) TTL column."""
    o = _order(_basic_grid())
    red = next(l for l in o.lines if l.color_code == "RED")
    assert red.qty == 60, red.qty                     # 10+20+30, not 999
    assert sum(red.size_breakdown.values()) == 60


def test_no_state_leakage():
    """BLU has smaller sizes; it must NOT inherit RED's larger quantities."""
    o = _order(_basic_grid())
    blu = next(l for l in o.lines if l.color_code == "BLU")
    assert blu.qty == 15, blu.qty
    assert blu.size_breakdown == {"S": 5, "M": 5, "L": 5}


def test_blank_rows_tolerated():
    o = _order(_basic_grid(blank_rows=True))
    assert len(o.lines) == 3
    assert {l.style for l in o.lines} == {"ST-001", "ST-002"}


def test_shifted_columns():
    """Two leading blank columns must not break detection (no fixed indices)."""
    o = _order(_basic_grid(lead_blank_cols=2))
    assert len(o.lines) == 3
    red = next(l for l in o.lines if l.color_code == "RED")
    assert red.qty == 60


def test_different_size_sets():
    """A second style with a completely different size set is parsed independently."""
    rows = [
        [None,     None,  "TTL", None,  None,  None,  None],
        [None,     None,  None,  "XS",  "S",   "28",  "30"],
        ["AA-100", "TTL", 0,     4,     6,     0,     0],
        [None,     "BLK",  0,     4,     6,     None,  None],
        ["BB-200", "TTL", 0,     0,     0,     11,    22],
        [None,     "NVY",  0,     None,  None,  11,    22],
    ]
    o = _order(GridSheet.from_matrix("S", rows))
    blk = next(l for l in o.lines if l.color_code == "BLK")
    nvy = next(l for l in o.lines if l.color_code == "NVY")
    assert blk.size_breakdown == {"XS": 4, "S": 6}
    assert nvy.size_breakdown == {"28": 11, "30": 22}
    assert nvy.qty == 33


def test_extra_notes_row_ignored():
    """A stray note row (no color code) between colors must be skipped."""
    rows = [
        [None,     None,  "TTL", None, None, None],
        [None,     None,  None,  "S",  "M",  "L"],
        ["ST-001", "TTL", 0,     1,    1,    1],
        [None,     "RED",  0,     10,   10,   10],
        [None,     None,   None,  None, None, None],   # blank/note
        [None,     "BLU",  0,     5,    5,    5],
    ]
    o = _order(GridSheet.from_matrix("S", rows))
    assert {l.color_code for l in o.lines} == {"RED", "BLU"}


def test_validator_duplicate_color():
    o = CanonicalOrder(document_type="PO")
    o.lines = [
        OrderLine(style="ST-1", color_code="RED", size_breakdown={"S": 5}, qty=5),
        OrderLine(style="ST-1", color_code="RED", size_breakdown={"S": 3}, qty=3),
    ]
    issues = POValidator().validate(o)
    assert any(i.code == "duplicate_color" for i in issues)


def test_validator_color_total_mismatch():
    o = CanonicalOrder(document_type="PO")
    o.lines = [OrderLine(style="ST-1", color_code="RED", size_breakdown={"S": 5, "M": 5}, qty=99)]
    issues = POValidator().validate(o)
    assert any(i.code == "color_total_mismatch" for i in issues)


def test_validator_style_total_reconciliation():
    o = CanonicalOrder(document_type="PO")
    o.lines = [
        OrderLine(style="ST-1", color_code="RED", size_breakdown={"S": 10}, qty=10),
        OrderLine(style="ST-1", color_code="BLU", size_breakdown={"S": 20}, qty=20),
    ]
    # declared style total (from TTL row) says 40, but colors sum to 30 → warning
    issues = POValidator().validate(o, declared_style_totals={"ST-1": 40})
    assert any(i.code == "style_total_mismatch" for i in issues)


def test_missing_fields_reported():
    o = CanonicalOrder(document_type="PO")
    o.lines = [OrderLine(style="", color_code="RED", size_breakdown={"S": 5}, qty=5)]
    issues = POValidator().validate(o)
    assert any(i.code == "missing_style" for i in issues)


# ── standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
