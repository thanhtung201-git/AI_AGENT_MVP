"""
parser.py — POParser: turn a workbook into a CanonicalOrder using structure,
not position.

Block algorithm (per sheet):
  Detect Style block  → a row whose STYLE column holds an article code starts a new
                        style (this is the style's aggregate/TTL row — NOT a color).
                        Reset all per-color state.
  Detect Color        → a subsequent row with the STYLE column blank and the COLOR
                        column non-empty is a color of the current style.
  Extract Size Qty    → read only the detected SIZE columns (subtotal columns excluded).
  Color Total         → SUM of the size quantities (never the style TTL column).
  Next color / style  → repeat; blank rows are skipped.

Produces the shared CanonicalOrder model — the GO generator never sees Excel.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from backend.go_compare.canonical import CanonicalOrder, OrderLine, Source, FieldValue
from backend.go_compare.po_parser.grid import (
    GridSheet, col_letter, is_blank, as_number, as_date, looks_like_article_code,
)
from backend.go_compare.po_parser.structure import StructureDetector, Structure

logger = logging.getLogger(__name__)


class POParser:
    """Deterministic, structure-based PO → CanonicalOrder parser."""

    def __init__(self, document_label: str = "PO"):
        self.document_label = document_label
        self.detector = StructureDetector()

    # ── public API ────────────────────────────────────────────────────────────

    def parse_workbook(self, workbook) -> CanonicalOrder:
        """Parse an openpyxl workbook (all sheets) into one CanonicalOrder."""
        order = CanonicalOrder(document_type="PO")
        for ws in workbook.worksheets:
            sheet = GridSheet.from_worksheet(ws)
            self._parse_sheet(sheet, order)
        self._fill_header_fields(order)
        return order

    def parse_sheet(self, sheet: GridSheet) -> CanonicalOrder:
        """Parse a single GridSheet (used by tests)."""
        order = CanonicalOrder(document_type="PO")
        self._parse_sheet(sheet, order)
        self._fill_header_fields(order)
        return order

    # ── per-sheet ─────────────────────────────────────────────────────────────

    def _parse_sheet(self, sheet: GridSheet, order: CanonicalOrder) -> None:
        st = self.detector.detect(sheet)
        if not st or not st.is_valid():
            logger.info(f"POParser: no parseable structure in sheet '{sheet.name}'")
            return

        # ── per-style state (reset on each new style) ──────────────────────────
        cur_style: str = ""
        cur_delivery: str = ""
        cur_order_date: str = ""
        cur_block: int = 0
        blocks_seen: dict = {}

        for r in range(st.first_data_row, sheet.n_rows):
            if sheet.row_is_blank(r):
                continue

            style_cell = sheet.cell(r, st.style_col) if st.style_col is not None else None

            # ── new Style block ────────────────────────────────────────────────
            if looks_like_article_code(style_cell):
                cur_style = str(style_cell).strip()
                cur_delivery = self._read_delivery(sheet, r, st)
                cur_order_date = self._read_date(sheet, r, st.order_date_col)
                # A style may be ordered more than once (a dated run and a STOCK run).
                # Each style-row occurrence opens a new block — they must stay apart,
                # because each becomes its own lot downstream.
                blocks_seen[cur_style] = blocks_seen.get(cur_style, 0) + 1
                cur_block = blocks_seen[cur_style]
                # aggregate/TTL row — do NOT emit a color line; state is reset here.
                continue

            if not cur_style:
                continue  # data before any style header — skip

            # ── Color row ──────────────────────────────────────────────────────
            color_cell = sheet.cell(r, st.color_col) if st.color_col is not None else None
            if is_blank(color_cell):
                continue
            color = str(color_cell).strip()

            # per-color state is freshly computed each iteration → no leakage.
            # Split by destination: the ERP opens one lot per market, so a colour row
            # spanning KOREA/TAIWAN/… is several order lines, not one aggregate.
            by_dest: dict = {}
            for sc in st.size_cols:
                q = as_number(sheet.cell(r, sc.index))
                if q is None or q == 0:
                    continue
                sizes = by_dest.setdefault(sc.destination, {})
                sizes[sc.label] = sizes.get(sc.label, 0.0) + q

            row_delivery = self._read_delivery(sheet, r, st) or cur_delivery
            row_order_date = self._read_date(sheet, r, st.order_date_col) or cur_order_date

            # A real order colour always carries quantities. A colour row that sums
            # to zero everywhere is not an order line — it is a repeated header band
            # mid-sheet (e.g. "Color Code" bleeding from a merged header) or an empty
            # row, and `by_dest` stays empty for it.
            for dest, size_breakdown in by_dest.items():
                color_total = sum(size_breakdown.values())  # DYNAMIC — never the TTL column
                if color_total <= 0:
                    continue
                order.lines.append(OrderLine(
                    style=cur_style,
                    block=cur_block,
                    color_code=color,
                    color_name="",
                    size_breakdown=size_breakdown,
                    qty=color_total,
                    order_date=row_order_date,
                    delivery_date=row_delivery,
                    destination=dest,
                    source=Source(
                        document=self.document_label,
                        sheet=sheet.name,
                        cell=f"row {r + 1}",
                        confidence="high",
                    ),
                ))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _read_delivery(self, sheet: GridSheet, r: int, st: Structure) -> str:
        return self._read_date(sheet, r, st.delivery_col)

    def _read_date(self, sheet: GridSheet, r: int, col: Optional[int]) -> str:
        if col is None:
            return ""
        d = as_date(sheet.cell(r, col))
        return d.strftime("%Y-%m-%d") if d else ""

    def _fill_header_fields(self, order: CanonicalOrder) -> None:
        """Populate top-level style/delivery from the parsed lines (deterministic)."""
        if not order.lines:
            return
        styles = []
        for l in order.lines:
            if l.style and l.style not in styles:
                styles.append(l.style)
        if styles:
            order.style = FieldValue(
                value=styles[0] if len(styles) == 1 else " / ".join(styles),
                source=Source(document=self.document_label, confidence="high"),
            )
        deliveries = [l.delivery_date for l in order.lines if l.delivery_date]
        if deliveries:
            order.delivery_date = FieldValue(
                value=deliveries[0],
                source=Source(document=self.document_label, confidence="medium"),
            )
        order_dates = [l.order_date for l in order.lines if l.order_date]
        if order_dates:
            order.order_date = FieldValue(
                value=order_dates[0],
                source=Source(document=self.document_label, confidence="medium"),
            )
