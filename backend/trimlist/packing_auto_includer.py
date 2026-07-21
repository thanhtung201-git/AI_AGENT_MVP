"""
packing_auto_includer.py — Phase 3.5: Auto-include standard packing items from Trim Master.

Problem:
  The Tech Pack BOM only lists garment materials (fabric, lining, thread, buttons, labels).
  Standard packing items (polybag, carton sticker, silica gel, collar band, clip, etc.)
  are NOT in the Tech Pack — they come from the Trim Master database.

Solution:
  Ask the LLM to identify which Trim Master items are "standard for all orders" and
  should be auto-included in every trimlist, regardless of what the Tech Pack says.

Zero hardcoded item names — the LLM decides based on semantic understanding of the data.
"""
import logging
from typing import Any, Dict, List

from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a garment merchandising specialist. "
    "Return valid JSON only. No markdown, no explanation."
)

_IDENTIFY_PROMPT = """
You have two data sources for a garment trimlist:

SOURCE A — Items already extracted from the Tech Pack BOM:
{tech_pack_names}

SOURCE B — Full Trim Master database (all items this buyer uses across orders):
{master_items}

YOUR TASK:
Identify which Trim Master items are STANDARD PACKING items that should be
auto-included in EVERY trimlist for this buyer, EVEN IF NOT mentioned in the Tech Pack.

Standard packing = items that apply to all garment types without variation:
  - Polybag / polyethylene bag
  - Carton sticker / box label
  - Barcode sticker
  - Tissue paper / product paper
  - Silica gel / moisture absorber
  - Sealing sticker / tape
  - Collar band / color band — INCLUDE EVERY variant present in the Trim Master:
    elastic color band, plastic color band, paper color band (they are separate rows)
  - Clips / plastic clips / butterfly pin
  - Verify sticker / security label
  - Extra button bag
  - Hang tag / price tag / main tag (if standard for all orders)
  - Cardboard / board

TAKE THE CODE FROM THE EXACT MATCHING ROW:
  - Copy material_code / supplier ONLY from the Trim Master row that IS this item.
  - Never reuse one code for several items. If a row has no code, return null — do
    not borrow a code from a different row.

NOT standard (exclude — these vary by style or season):
  - Items already in the Tech Pack (listed in SOURCE A)
  - Style-specific labels (care label, brand label, size label — already in BOM)
  - Fabric, interlining, thread (construction materials)
  - RFID tag if buyer provides (mark as "Buyer provide")

For each standard packing item found, return:
- material_name  : exact name from Trim Master
- material_code  : code from Trim Master (null if none)
- supplier       : supplier name
- category       : always "PACKING"
- consumption    : quantity per garment from Trim Master (e.g. "1EA", "2PCS")
- remark         : remark from Trim Master if any
- source_ref     : "Trim Master — auto-include"

TECH PACK ITEMS (already included — do NOT duplicate these):
{tech_pack_names}

Return JSON:
{{
  "standard_packing": [
    {{
      "material_name":  "26SS New LDPE Recycled resin polybag",
      "material_code":  "441025179X",
      "supplier":       "TESSELLATION",
      "category":       "PACKING",
      "consumption":    "1EA",
      "remark":         "26SS NEW QUALITY",
      "source_ref":     "Trim Master — auto-include"
    }}
  ]
}}

If no standard packing items are found (e.g. Trim Master only has garment materials),
return: {{"standard_packing": []}}
"""


class PackingAutoIncluder:
    """
    Phase 3.5: Identifies and adds standard packing items from Trim Master
    that are not explicitly listed in the Tech Pack BOM.

    Input : merged Tech Pack items + full Trim Master item list
    Output: additional packing items to append to the trimlist
    """

    def __init__(self):
        self.llm = GroqClient()

    def auto_include(
        self,
        merged_items: List[Dict],
        master_items: List[Dict],
    ) -> List[Dict]:
        """
        Return a list of standard packing items to add from Trim Master.
        Items already present in merged_items are excluded automatically.
        """
        if not master_items:
            return []

        # Names already in the trimlist (for dedup)
        existing_names = {
            (item.get("material_name") or "").lower().strip()
            for item in merged_items
        }
        existing_codes = {
            (item.get("material_code") or "").lower().strip()
            for item in merged_items
            if item.get("material_code")
        }

        try:
            packing_items = self._llm_identify(merged_items, master_items)
        except Exception as e:
            logger.warning(f"PackingAutoIncluder: LLM error (non-fatal): {e}")
            return []

        # Filter duplicates
        result = []
        for item in packing_items:
            name = (item.get("material_name") or "").lower().strip()
            code = (item.get("material_code") or "").lower().strip()
            if name in existing_names:
                continue
            if code and code in existing_codes:
                continue
            # Ensure required fields
            item.setdefault("category", "PACKING")
            item.setdefault("sources", {})
            item.setdefault("conflicts", [])
            item.setdefault("confidence", "master_auto")
            item.setdefault("master_match", item.get("material_name"))
            result.append(item)

        logger.info(
            f"PackingAutoIncluder: adding {len(result)} standard packing items "
            f"(from {len(packing_items)} identified, {len(packing_items)-len(result)} deduped)"
        )
        return result

    def _llm_identify(
        self, merged_items: List[Dict], master_items: List[Dict]
    ) -> List[Dict]:
        tp_names = "\n".join(
            f"- {item.get('material_name', '?')} ({item.get('category', '?')})"
            for item in merged_items
        )

        master_text_lines = []
        for i, m in enumerate(master_items[:200], 1):
            code = (m.get("supplier_code") or m.get("material_code") or "")[:60]
            qty  = m.get("qty_per_garment") or ""
            unit = m.get("unit") or ""
            supp = m.get("supplier") or ""
            rem  = (m.get("remark") or "")[:80]
            parts = [f"Row {i}: {m.get('trim_item', '?')}"]
            if code:   parts.append(f"  code: {code}")
            if supp:   parts.append(f"  supplier: {supp}")
            if qty:    parts.append(f"  qty: {qty} {unit}".strip())
            if rem:    parts.append(f"  remark: {rem}")
            master_text_lines.append("\n".join(parts))

        master_text = "\n\n".join(master_text_lines)

        prompt = _IDENTIFY_PROMPT.format(
            tech_pack_names=tp_names,
            master_items=master_text,
        )

        result = self.llm.extract_json_with_retry(
            system_prompt=_SYSTEM,
            user_content=prompt,
            max_retries=2,
        )

        items = result.get("standard_packing") or []
        return [i for i in items if isinstance(i, dict) and i.get("material_name")]
