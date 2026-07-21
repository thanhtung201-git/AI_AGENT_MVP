"""
structure.py — StructureDetector: locate the header band and classify columns
using generic structural signals only (never fixed indices / names).

Signals used:
  - size-header row  : the row that maximizes "columns that are a short token AND
                       have several integer values in the rows below".
  - group-header row : the row directly above the size-header row (destination /
                       subtotal labels like KOREA / TAIWAN — read generically).
  - size columns     : columns non-empty in the size-header row.
  - subtotal columns : columns non-empty in the group-header row but empty in the
                       size-header row (destination totals + grand TTL) → excluded
                       from quantity sums.
  - style column     : column with the most article-code-shaped values in the body.
  - color column     : the text column (not style/size/subtotal) most populated on
                       rows where the style column is blank.
  - date columns     : columns whose body cells are dates; delivery = the later one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.go_compare.po_parser.grid import (
    GridSheet, col_letter, clean_token, is_blank, is_number, as_date,
    looks_like_article_code,
)


# A size label is a short token ("00S", "0XL"). Anything longer is a prose header
# (e.g. "DES. / COLOR CMNT") that happens to sit in the size-header band.
_MAX_SIZE_TOKEN = 10


@dataclass
class SizeColumn:
    index: int
    label: str          # size code, e.g. "00S"
    destination: str    # nearest group-header label to the left, e.g. "KOREA"


@dataclass
class Structure:
    group_header_row: int
    size_header_row: int
    first_data_row: int
    style_col: Optional[int]
    color_col: Optional[int]
    order_date_col: Optional[int]
    delivery_col: Optional[int]
    desc_col: Optional[int]
    size_cols: List[SizeColumn] = field(default_factory=list)
    subtotal_cols: List[int] = field(default_factory=list)

    def is_valid(self) -> bool:
        return bool(self.size_cols) and self.style_col is not None and self.color_col is not None


class StructureDetector:

    def detect(self, sheet: GridSheet) -> Optional[Structure]:
        if sheet.n_rows < 2 or sheet.n_cols < 2:
            return None

        size_row = self._find_size_header_row(sheet)
        if size_row is None:
            return None
        group_row = size_row - 1 if size_row - 1 >= 0 else size_row
        first_data = size_row + 1

        size_cols, subtotal_cols = self._classify_columns(sheet, group_row, size_row, first_data)

        # The quantity region begins at the first subtotal/TTL column. Anything with a
        # numeric body to the LEFT of it (e.g. an order-sequence "NO" column) is metadata,
        # not a size — drop such spurious size columns generically.
        if subtotal_cols:
            first_qty = min(subtotal_cols)
            size_cols = [s for s in size_cols if s.index > first_qty]

        if not size_cols:
            return None

        first_size_idx = min(sc.index for sc in size_cols)
        style_col = self._find_style_col(sheet, first_data, first_size_idx)
        color_col = self._find_color_col(sheet, first_data, first_size_idx, style_col,
                                         {sc.index for sc in size_cols} | set(subtotal_cols))
        order_date_col, delivery_col = self._find_date_cols(sheet, first_data)
        desc_col = self._find_desc_col(sheet, first_data, first_size_idx, style_col, color_col)

        return Structure(
            group_header_row=group_row, size_header_row=size_row, first_data_row=first_data,
            style_col=style_col, color_col=color_col,
            order_date_col=order_date_col, delivery_col=delivery_col,
            desc_col=desc_col, size_cols=size_cols, subtotal_cols=subtotal_cols,
        )

    # ── header band ───────────────────────────────────────────────────────────

    def _find_size_header_row(self, sheet: GridSheet, scan_rows: int = 20) -> Optional[int]:
        """The size-header row has many short-token columns that carry integers below."""
        best_row, best_score = None, 0
        limit = min(scan_rows, sheet.n_rows - 1)
        for r in range(limit):
            score = 0
            for c in range(sheet.n_cols):
                raw = sheet.cell(r, c)
                # A size-header cell is a TEXT label (e.g. "00S"), never a bare number —
                # this is what separates the header row from the numeric data rows.
                if is_number(raw):
                    continue
                tok = clean_token(raw)
                if not tok or len(tok) > _MAX_SIZE_TOKEN:
                    continue
                # the column must carry integer quantities in the rows below
                ints = sum(
                    1 for rr in range(r + 1, min(r + 8, sheet.n_rows))
                    if is_number(sheet.cell(rr, c))
                )
                if ints >= 2:
                    score += 1
            if score > best_score:
                best_row, best_score = r, score
        # need at least a couple of size columns to be a real size band
        return best_row if best_score >= 2 else None

    # ── column classification ─────────────────────────────────────────────────

    def _classify_columns(self, sheet, group_row, size_row, first_data):
        size_cols: List[SizeColumn] = []
        subtotal_cols: List[int] = []
        last_group_label = ""
        for c in range(sheet.n_cols):
            group_tok = clean_token(sheet.cell(group_row, c)) if group_row != size_row else ""
            size_tok = clean_token(sheet.cell(size_row, c))
            if group_tok:
                last_group_label = group_tok
            # A cell merged down both header rows (group_tok == size_tok) labels a
            # metadata column — style, colour, order no — not part of the quantity
            # grid. Real size columns carry a size label under a destination; real
            # subtotal columns carry a destination label and no size label.
            if group_tok and group_tok == size_tok:
                continue
            # Scan every data row: a size ordered only by a late style (e.g. 0XS on
            # row 60) is still a size column, and dropping it silently loses its qty.
            has_numeric_body = any(
                is_number(sheet.cell(r, c))
                for r in range(first_data, sheet.n_rows)
            )
            if size_tok and len(size_tok) <= _MAX_SIZE_TOKEN and has_numeric_body:
                # a real size column carries quantities; merged label columns
                # (which also bleed into the size-header row) have no numeric body.
                size_cols.append(SizeColumn(index=c, label=size_tok, destination=last_group_label))
            elif group_tok and has_numeric_body:
                # labeled in group row, no size label → destination subtotal / grand total
                subtotal_cols.append(c)
        return size_cols, subtotal_cols

    def _find_style_col(self, sheet, first_data, first_size_idx) -> Optional[int]:
        best_col, best = None, 0
        for c in range(first_size_idx):
            cnt = sum(
                1 for r in range(first_data, sheet.n_rows)
                if looks_like_article_code(sheet.cell(r, c))
            )
            if cnt > best:
                best_col, best = c, cnt
        return best_col if best > 0 else None

    def _find_color_col(self, sheet, first_data, first_size_idx, style_col, reserved) -> Optional[int]:
        """Text column (not style/size/subtotal) most populated on style-blank rows."""
        best_col, best = None, 0
        for c in range(first_size_idx):
            if c == style_col or c in reserved:
                continue
            cnt = 0
            for r in range(first_data, sheet.n_rows):
                # only look at color rows (style column blank)
                if style_col is not None and not is_blank(sheet.cell(r, style_col)):
                    continue
                v = sheet.cell(r, c)
                if is_blank(v) or is_number(v):
                    continue
                if len(str(v).strip()) <= 20:
                    cnt += 1
            if cnt > best:
                best_col, best = c, cnt
        return best_col if best > 0 else None

    def _find_date_cols(self, sheet, first_data):
        """Classify the date columns: order date is the EARLIEST, delivery the LATEST.

        A buying sheet carries both an order-placement date (발주 / PO date) and a
        target-delivery date. When only one date column exists it is the delivery
        date and order date is unknown (their ERP fills the rest)."""
        cand: Dict[int, list] = {}
        for c in range(sheet.n_cols):
            dates = [as_date(sheet.cell(r, c)) for r in range(first_data, sheet.n_rows)]
            dates = [d for d in dates if d]
            if dates:
                cand[c] = dates
        if not cand:
            return None, None
        delivery = max(cand, key=lambda c: max(cand[c]))
        order = min(cand, key=lambda c: min(cand[c]))
        if order == delivery:
            return None, delivery  # single date column → treat as delivery only
        return order, delivery

    def _find_desc_col(self, sheet, first_data, first_size_idx, style_col, color_col) -> Optional[int]:
        best_col, best = None, 0
        for c in range(first_size_idx):
            if c in (style_col, color_col):
                continue
            cnt = sum(
                1 for r in range(first_data, sheet.n_rows)
                if isinstance(sheet.cell(r, c), str) and len(sheet.cell(r, c).strip()) > 12
            )
            if cnt > best:
                best_col, best = c, cnt
        return best_col
