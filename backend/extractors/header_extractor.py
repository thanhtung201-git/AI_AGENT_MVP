import re
import logging
from backend.utils.groq_client import GroqClient
from backend.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# Maps PDF form field names → canonical header field names.
# Based on the observed form field output:
#   Text1  = po_number,  Text2  = order_date
#   Text3  = buyer_name, Text4  = buyer_address_street
#   Text5  = buyer_address_city, Text6 = buyer_phone
#   Text7  = vendor_name, Text8  = vendor_address
#   Text9  = vendor_email, Text10 = vendor_phone
#   Text77 = delivery_date
_FIELD_MAP = {
    "Text1":  "po_number",
    "Text2":  "order_date",
    "Text3":  "buyer_name",
    "Text4":  "buyer_address_street",
    "Text5":  "buyer_address_city",
    "Text6":  "buyer_phone",
    "Text7":  "vendor_name",
    "Text8":  "vendor_address",
    "Text9":  "vendor_email",
    "Text10": "vendor_phone",
    "Text77": "delivery_date",
    "Text74": "shipping_method",
    "Text75": "shipping_company",
    "Text76": "tracking_number",
    "Text78": "subtotal",
    "Text79": "discount",
    "Text80": "tax",
    "Text81": "shipping_cost",
    "Text82": "payment_type",
    "Text83": "total_amount",
    "Text84": "notes",
}


class HeaderExtractor:
    """Parses PO header fields. Uses Groq LLM when available, regex fallback otherwise."""

    def __init__(self):
        self.groq_client = GroqClient()
        self.system_prompt = None
        try:
            self.system_prompt = PromptManager.load_prompt("header_prompt.txt")
        except FileNotFoundError:
            logger.warning(
                "header_prompt.txt not found — LLM extraction disabled, "
                "regex fallback will be used."
            )

    def extract(self, raw_text: str) -> dict:
        """
        Extract header fields from raw PDF text.

        Tries Groq LLM first; falls back to regex parsing of form fields.

        Args:
            raw_text: String content from the PDF extractor.

        Returns:
            Dict of canonical header fields, e.g.:
            {
                "po_number": "123456/22",
                "order_date": "22ND SEPTEMBER, 2022",
                "buyer_name": "FASHION QUEEN",
                ...
            }
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Empty raw text provided for header extraction.")
            return {}

        # ── Try LLM first ────────────────────────────────────────────────────
        if self.system_prompt:
            try:
                result = self.groq_client.extract_json(
                    system_prompt=self.system_prompt,
                    user_content=raw_text,
                )
                if result:
                    logger.info("Header extracted via LLM.")
                    return result
            except Exception as e:
                logger.warning(f"LLM header extraction failed ({e}). Using regex fallback.")

        # ── Regex fallback ───────────────────────────────────────────────────
        return self._regex_extract(raw_text)

    # ------------------------------------------------------------------ #

    def _regex_extract(self, text: str) -> dict:
        """
        Parse named form fields from the PDF text block:
            --- DỮ LIỆU TỪ Ô FORM ĐIỀN SẴN ---
            Text1: 123456/22
            Text3: FASHION QUEEN
            ...
        """
        # Find the form-fields section if present; otherwise scan the whole text.
        form_section_match = re.search(
            r"---\s*DỮ LIỆU TỪ Ô FORM.*?---\n(.*?)(?=\n---|$)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        scan_text = form_section_match.group(1) if form_section_match else text

        # Extract all TextN: value pairs
        raw_fields: dict[str, str] = {}
        for match in re.finditer(r"^(Text\d+):\s*(.+)$", scan_text, re.MULTILINE):
            key, value = match.group(1), match.group(2).strip()
            raw_fields[key] = value

        if not raw_fields:
            logger.warning("Regex fallback: no form fields found in text.")
            return {}

        # Map to canonical field names
        header: dict[str, str] = {}
        for field_key, canonical_name in _FIELD_MAP.items():
            if field_key in raw_fields:
                header[canonical_name] = raw_fields[field_key]

        # Combine address parts into a single string if both present
        street = header.pop("buyer_address_street", "")
        city = header.pop("buyer_address_city", "")
        if street or city:
            header["buyer_address"] = ", ".join(filter(None, [street, city]))

        # Clean up vendor name (strip trailing contact info after double-space)
        if "vendor_name" in header:
            header["vendor_name"] = re.split(r"\s{2,}", header["vendor_name"])[0].strip()

        logger.info(f"Header extracted via regex: {list(header.keys())}")
        return header