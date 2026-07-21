"""
document_reader.py — LLM-driven reader that maps ANY order document into the
canonical schema. Used for both the PO and the generated GO.

The LLM is given the document as a structured text dump (with cell references
for Excel) and asked to identify garment-order concepts SEMANTICALLY — it is
never told where fields live. Works for any brand / layout / language.

Python does: file reading, chunking, orchestration, JSON→dataclass mapping.
LLM does:    semantic understanding, field identification, traceability.
"""
import logging
from typing import Any, Dict, List

from backend.utils.groq_client import GroqClient
from backend.go_compare.canonical import CanonicalOrder, order_from_llm

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a garment-industry order-document analyst. You read purchase orders, "
    "buying sheets, and order-confirmation exports from ANY brand or ERP, in any "
    "layout or language. You identify order concepts by MEANING, never by fixed "
    "position. Return valid JSON only — no markdown, no commentary."
)

_EXTRACT_PROMPT = """
Below is a garment order document dumped as structured text. For spreadsheets, each
value is prefixed with its cell reference (e.g. "D25=774") and grouped by sheet.

YOUR TASK: Understand the document semantically and map it to the canonical schema.
Identify these concepts wherever they appear — do NOT assume any fixed location:
  - PO number / purchase order number
  - GO number / order-confirmation number (may be absent)
  - Buyer / brand / customer
  - Style / style number / article (there may be MULTIPLE styles)
  - Season
  - Factory / vendor / supplier
  - Order date / buyer PO date / order-placement date (Korean "발주") — the date the
    order was PLACED, distinct from and usually EARLIER than the delivery date
  - Delivery / ship / due / target-delivery date
  - Order lines: each combination of style × color × size (or color-level totals)
    with its quantity, and per-size breakdown when the sheet has size columns.

RULES:
  - A document may contain MANY styles and MANY colors. Capture every order line.
  - Colors often appear as short codes (N2, W2, B2) and/or names. Capture both if present.
  - Size columns are frequently labeled with codes like 00S/00M/00L/0XL. When a row
    has per-size quantities, put them in "size_breakdown": {{"00S": 175, "00M": 252}}.
  - "TTL"/"TOTAL"/"SUBTOTAL" rows are AGGREGATES that sum the per-color rows beneath
    them. DO NOT emit an order line for a TTL/TOTAL row — it would double-count the
    quantity. Only emit the granular per-color (and per-size) lines. Still READ the
    style / delivery date / season carried on a TTL row and attach them to the
    per-color lines that belong to it.
  - A buying sheet is organized as STYLE BLOCKS: a header row introduces a style
    (its article code + a TTL row), followed by several color rows. The style code
    usually appears ONLY on the block's header/TTL row; the color rows below leave it
    blank. You MUST carry the block's style code down to EVERY color line in that block.
    Assign each color line to the style block it physically sits under — never to a
    different style, and never leave a color line's "style" empty.
  - The "style" is the PRODUCT ARTICLE CODE (e.g. "HZSH6F201", "HZSH6C331"). Do NOT
    confuse it with the neighbouring ORDER-TYPE / SEQUENCE column, whose values are
    short markers like "01", "02", "STOCK", "SMS", "BULK", "SS", "MAIN". Those are
    order types, NOT styles. If a cell you were about to use as "style" is one of these
    short order-type markers or is purely numeric, it is NOT the style — look up to the
    block header for the real article code instead.
  - Capture EVERY style block in the document. A buying sheet typically contains many
    styles; do not stop after the first one.
  - Distinguish real order quantities from targets, retail prices, or sample counts.
  - If a value is genuinely absent, use null. Never invent values.
  - For EVERY value, give a source: the sheet name and the cell reference you read it
    from, plus a confidence ("high"/"medium"/"low").

Return JSON in EXACTLY this shape:
{{
  "po_number": {{"value": "...", "source": {{"sheet": "...", "cell": "...", "confidence": "high"}}}},
  "go_number": {{"value": null, "source": {{"sheet": "", "cell": "", "confidence": "low"}}}},
  "buyer":     {{"value": "...", "source": {{"sheet": "...", "cell": "...", "confidence": "high"}}}},
  "style":     {{"value": "...", "source": {{"sheet": "...", "cell": "...", "confidence": "medium"}}}},
  "season":    {{"value": "...", "source": {{"sheet": "...", "cell": "...", "confidence": "medium"}}}},
  "factory":   {{"value": "...", "source": {{"sheet": "...", "cell": "...", "confidence": "low"}}}},
  "order_date":    {{"value": "...", "source": {{"sheet": "...", "cell": "...", "confidence": "medium"}}}},
  "delivery_date": {{"value": "...", "source": {{"sheet": "...", "cell": "...", "confidence": "medium"}}}},
  "lines": [
    {{
      "style": "...",
      "color_code": "N2",
      "color_name": "...",
      "size": "",
      "size_breakdown": {{"00S": 175, "00M": 252, "00L": 168}},
      "qty": 774,
      "delivery_date": "...",
      "destination": "",
      "source": {{"sheet": "...", "cell": "row 16", "confidence": "high"}}
    }}
  ]
}}

DOCUMENT ({document_label}):
{document_text}
"""


class DocumentReader:
    """Reads any order document into a CanonicalOrder via LLM semantic extraction."""

    def __init__(self):
        self.llm = GroqClient()

    def read(self, file_path: str, document_type: str, document_label: str) -> CanonicalOrder:
        """
        Args:
            file_path      : path to PO/GO file (xlsx, pdf, ...)
            document_type  : "PO" | "GO"
            document_label : human label used in traceability (e.g. "PO", "GO Information")

        Strategy: for spreadsheets, try the deterministic structure-based POParser
        first (fast, reproducible, correct color totals). Fall back to the LLM reader
        when the file is not a grid or has no detectable structure.
        """
        if str(file_path).lower().endswith((".xlsx", ".xls", ".xlsm")):
            parsed = self._try_structured(file_path, document_type, document_label)
            if parsed is not None and parsed.lines:
                logger.info(
                    f"DocumentReader[{document_label}]: structured parser → "
                    f"{len(parsed.lines)} lines, total_qty={parsed.total_qty():.0f}"
                )
                return parsed
            logger.info(f"DocumentReader[{document_label}]: structured parser found nothing, using LLM")

        raw_text = self._read_raw(file_path)
        if not raw_text:
            logger.warning(f"DocumentReader: empty text from {file_path}")
            return CanonicalOrder(document_type=document_type)

        merged: Dict[str, Any] = {"lines": []}
        for chunk in self._chunk(raw_text, max_chars=14000):
            part = self._llm_extract(chunk, document_label)
            self._merge(merged, part)

        order = order_from_llm(merged, document_type, document_label)
        logger.info(
            f"DocumentReader[{document_label}]: {len(order.lines)} lines, "
            f"total_qty={order.total_qty():.0f}, style={order.style.value}"
        )
        return order

    # ── structured (deterministic) path ───────────────────────────────────────

    def _try_structured(self, file_path, document_type, document_label):
        try:
            import openpyxl
            from backend.go_compare.po_parser.parser import POParser
            # rich_text=True so we can see per-run strikethrough and drop crossed-out
            # (obsolete) values like a colour code the buyer revised in place.
            wb = openpyxl.load_workbook(file_path, data_only=True, rich_text=True)
            order = POParser(document_label=document_label).parse_workbook(wb)
            order.document_type = document_type
            return order
        except Exception as e:
            logger.warning(f"DocumentReader structured parse failed ({e}); falling back to LLM")
            return None

    # ── raw reading ───────────────────────────────────────────────────────────

    def _read_raw(self, file_path: str) -> str:
        try:
            from tools.reader import read_file
            r = read_file(file_path)
            if r.get("success"):
                return r.get("text") or ""
            logger.error(f"DocumentReader read_file failed: {r.get('error')}")
        except Exception as e:
            logger.error(f"DocumentReader raw read exception: {e}")
        return ""

    # ── LLM ───────────────────────────────────────────────────────────────────

    def _llm_extract(self, document_text: str, document_label: str) -> Dict[str, Any]:
        try:
            prompt = _EXTRACT_PROMPT.format(
                document_label=document_label,
                document_text=document_text,
            )
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=2,
            )
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.warning(f"DocumentReader LLM error: {e}")
            return {}

    # ── merge chunk results ───────────────────────────────────────────────────

    @staticmethod
    def _merge(base: Dict[str, Any], part: Dict[str, Any]) -> None:
        if not part:
            return
        # Scalar header fields: keep first non-null seen
        for k in ("po_number", "go_number", "buyer", "style", "season", "factory", "order_date", "delivery_date"):
            if k not in base or _is_empty(base.get(k)):
                if not _is_empty(part.get(k)):
                    base[k] = part[k]
        # Lines accumulate
        base.setdefault("lines", [])
        base["lines"].extend(part.get("lines") or [])

    # ── chunking ──────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk(text: str, max_chars: int) -> List[str]:
        if len(text) <= max_chars:
            return [text]
        chunks, cur = [], ""
        for line in text.splitlines(keepends=True):
            if len(cur) + len(line) > max_chars and cur:
                chunks.append(cur)
                cur = line
            else:
                cur += line
        if cur:
            chunks.append(cur)
        return chunks


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, dict):
        return _is_empty(v.get("value"))
    return str(v).strip() == ""
