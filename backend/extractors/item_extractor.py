from __future__ import annotations
import re
import logging
from typing import List, Dict, Any
from backend.utils.groq_client import GroqClient
from backend.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# Each item row in the PDF occupies 7 consecutive TextN fields:
#   +0 = style_name  (PRODUCT NAME)
#   +1 = style_code  (ITEM #)
#   +2 = unit_price  (PRICE)
#   +3 = qty         (QTY)
#   +4 = size        (SIZE)
#   +5 = color_name  (COLOUR)
#   +6 = total_price (TOTAL)
#
# Known item groups from the test PDF:
#   Item 1: Text11–Text17  (Poshmark black dress)
#   Item 2: Text18–Text24  (Waterproof French overcoat)
#   Item 3: Text25–Text31  (Signature perfume)
#   Item 4: Text32–Text38  (Classic blazer)
#
# We detect groups automatically so this works for any number of items.

_ITEM_FIELD_OFFSET = {
    0: "style_name",
    1: "style_code",
    2: "unit_price",
    3: "total_quantity",
    4: "size",
    5: "color_name",
    6: "total_price",
}

# Known first-field numbers for item groups (Text11, Text18, Text25, Text32, …)
# Pattern: first item starts at Text11, then groups of 7.
_ITEM_GROUP_START = 11
_ITEM_GROUP_SIZE  = 7
_ITEM_GROUP_COUNT = 10   # support up to 10 item rows; extras are ignored if empty


class ItemExtractor:
    """Parses PO line items. Uses Groq LLM when available, regex fallback otherwise."""

    def __init__(self):
        self.groq_client = GroqClient()
        self.system_prompt = None
        try:
            self.system_prompt = PromptManager.load_prompt("item_prompt.txt")
        except FileNotFoundError:
            logger.warning(
                "item_prompt.txt not found — LLM extraction disabled, "
                "regex fallback will be used."
            )

    def extract(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Extract line items from raw PDF text.

        Returns a list of dicts compatible with POItem fields:
        [
            {
                "style_name": "Poshmark black dress",
                "style_code": "99880052",
                "unit_price": 1080.0,
                "total_quantity": 1,
                "size_breakdown": {"M": 1},
                "color_name": "BLACK",
                "total_price": 1080.0,
            },
            ...
        ]
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Empty raw text provided for item extraction.")
            return []

        # ── Try LLM first ────────────────────────────────────────────────────
        if self.system_prompt:
            try:
                result = self.groq_client.extract_json(
                    system_prompt=self.system_prompt,
                    user_content=raw_text,
                )
                if result:
                    items = result if isinstance(result, list) else result.get("items", [])
                    if items:
                        logger.info(f"Items extracted via LLM: {len(items)} items.")
                        return items
            except Exception as e:
                logger.warning(f"LLM item extraction failed ({e}). Using regex fallback.")

        # ── Regex fallback ───────────────────────────────────────────────────
        return self._regex_extract(raw_text)

    # ------------------------------------------------------------------ #

    def _regex_extract(self, text: str) -> List[Dict[str, Any]]:
        """Parse item rows from TextN form fields in the PDF text."""
        # Extract all TextN: value pairs from the form fields section
        form_section_match = re.search(
            r"---\s*DỮ LIỆU TỪ Ô FORM.*?---\n(.*?)(?=\n---|$)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        scan_text = form_section_match.group(1) if form_section_match else text

        raw_fields: Dict[str, str] = {}
        for match in re.finditer(r"^(Text(\d+)):\s*(.+)$", scan_text, re.MULTILINE):
            raw_fields[match.group(1)] = match.group(3).strip()

        if not raw_fields:
            logger.warning("Item regex fallback: no form fields found.")
            return []

        items: List[Dict[str, Any]] = []

        for group_index in range(_ITEM_GROUP_COUNT):
            start = _ITEM_GROUP_START + group_index * _ITEM_GROUP_SIZE
            group: Dict[str, str] = {}

            for offset, field_name in _ITEM_FIELD_OFFSET.items():
                key = f"Text{start + offset}"
                if key in raw_fields:
                    group[field_name] = raw_fields[key]

            # Skip empty rows (no style_name and no style_code)
            if not group.get("style_name") and not group.get("style_code"):
                continue

            item = self._parse_item_group(group)
            items.append(item)

        logger.info(f"Items extracted via regex: {len(items)} items.")
        return items

    def _parse_item_group(self, group: Dict[str, str]) -> Dict[str, Any]:
        """Convert a raw field group into a POItem-compatible dict."""
        item: Dict[str, Any] = {}

        if "style_name" in group:
            # Strip any quotes (e.g. Classic blazer "mindsweeper")
            item["style_name"] = group["style_name"].replace('"', '').strip()

        if "style_code" in group:
            item["style_code"] = group["style_code"].strip()

        if "color_name" in group:
            # "*" means unspecified in the test PDF
            raw_color = group["color_name"].strip()
            item["color_name"] = None if raw_color == "*" else raw_color

        # Numeric fields — coerce safely
        item["unit_price"]    = _to_float(group.get("unit_price"))
        item["total_price"]   = _to_float(group.get("total_price"))
        item["total_quantity"] = _to_int(group.get("total_quantity"))

        # Size: store as size_breakdown dict {size: qty} to match POItem schema
        size_raw = group.get("size", "").strip()
        qty      = item.get("total_quantity") or 1
        if size_raw and size_raw != "*":
            item["size_breakdown"] = {size_raw: qty}
        else:
            item["size_breakdown"] = None

        return item


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(re.sub(r"[^\d.]", "", value))
    except ValueError:
        return None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(re.sub(r"[^\d]", "", value))
    except ValueError:
        return None