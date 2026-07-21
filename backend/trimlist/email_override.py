"""
email_override.py — Step 4: Apply Email/Note instructions (HIGHEST PRIORITY).

Email instructions override everything that came before (Tech Pack, Trim Master, Buyer Rules).

The LLM:
  1. Reads the email/note text
  2. Identifies any instructions that modify trim items
  3. Applies modifications with the highest priority
  4. Can also ADD new items mentioned in email
  5. Records the exact email text that triggered each change

Examples:
  "Use YKK zipper instead of SBS" → override supplier on zipper rows
  "Add RFID label to all pieces"  → add new TrimRow for RFID label
  "Polybag must be biodegradable" → update spec on polybag row
"""
import json
import logging
from typing import Dict, List, Optional, Tuple

from backend.trimlist.traceability import TrimRow, TrimSource, classify_category, CATEGORY_ORDER
from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_SYSTEM = """You are a garment merchandising specialist applying email instructions to a trimlist.
Email instructions have the HIGHEST priority. Return valid JSON only."""

_PROMPT = """
Apply the following EMAIL/NOTE instructions to the TRIM LIST.
Email instructions have HIGHEST PRIORITY and override everything else.

EMAIL/NOTE CONTENT:
{email_text}

CURRENT TRIM LIST:
{trim_items}

INSTRUCTIONS:
1. Read the email carefully for ANY instruction that modifies a trim item.
2. For each modification:
   - Identify WHICH item is being modified (match by material name or type)
   - Identify WHICH field is being changed (supplier, spec, color, placement, etc.)
   - Record the exact sentence from the email that triggered this change
3. If the email adds a completely NEW item not in the trim list — add it.
4. If the email says to REMOVE an item — mark it as removed.
5. If the email is ambiguous or general (like "please confirm"), ignore it.

RETURN JSON:
{{
  "modifications": [
    {{
      "material_name":  "Zipper (Main)",
      "action":         "update",
      "field":          "supplier",
      "new_value":      "YKK",
      "email_trigger":  "Use YKK zipper instead of SBS",
      "reason":         "Buyer specifies YKK brand zipper"
    }}
  ],
  "new_items": [
    {{
      "category":       "LABEL",
      "material_name":  "RFID Label",
      "spec":           "RFID smart label",
      "placement":      "Inside back panel",
      "email_trigger":  "Add RFID label to all pieces",
      "source_ref":     "Email instruction"
    }}
  ],
  "removed_items": [],
  "summary": "1 modification applied, 0 new items added"
}}

If no instructions found: {{"modifications": [], "new_items": [], "removed_items": [], "summary": "No trim modifications found in email"}}
"""


class EmailOverride:
    """
    Applies email/note instructions to TrimRow list.
    Email has the highest priority — it can change any field or add/remove rows.
    """

    def __init__(self):
        self.llm = GroqClient()

    def apply(self, rows: List[TrimRow], email_text: str) -> Tuple[List[TrimRow], List[str]]:
        """
        Apply email instructions to rows.

        Returns:
            (updated_rows, list_of_changes_applied)
        """
        if not email_text or not email_text.strip():
            return rows, []

        items_text = json.dumps([
            {"material_name": r.material_name, "category": r.category,
             "supplier": r.supplier, "spec": r.spec, "placement": r.placement,
             "color": r.color}
            for r in rows
        ], ensure_ascii=False)

        result = self._call_llm(email_text, items_text)

        changes: List[str] = []

        # Apply modifications
        modifications  = result.get("modifications") or []
        mod_index = self._index_by_name(modifications, "material_name")
        for row in rows:
            key = row.material_name.lower().strip()
            mod = mod_index.get(key)
            if not mod:
                continue

            field     = mod.get("field") or ""
            new_value = mod.get("new_value")
            trigger   = mod.get("email_trigger") or ""

            if field and new_value:
                setattr_map = {
                    "supplier":   "supplier",
                    "spec":       "spec",
                    "placement":  "placement",
                    "color":      "color",
                    "remark":     "remark",
                    "material_code": "material_code",
                    "supplier_code": "supplier_code",
                    "consumption": "consumption",
                }
                attr = setattr_map.get(field.lower())
                if attr:
                    setattr(row, attr, new_value)
                    row.source.email_ref = trigger
                    changes.append(f"Updated {row.material_name}.{field} → '{new_value}' (from email: \"{trigger}\")")

        # Handle removed items
        removed_names = {
            (r.get("material_name") or "").lower().strip()
            for r in (result.get("removed_items") or [])
        }
        if removed_names:
            before = len(rows)
            rows = [r for r in rows if r.material_name.lower().strip() not in removed_names]
            changes.append(f"Removed {before - len(rows)} items per email instruction")

        # Add new items from email
        new_items = result.get("new_items") or []
        for item in new_items:
            name = str(item.get("material_name") or "").strip()
            if not name:
                continue
            category = item.get("category") or classify_category(name)
            trigger  = item.get("email_trigger") or ""
            row = TrimRow(
                category=category,
                sort_key=CATEGORY_ORDER.get(category, 99),
                material_name=name,
                spec=item.get("spec") or None,
                placement=item.get("placement") or None,
                color=item.get("color") or None,
                consumption=item.get("consumption") or None,
                source=TrimSource(
                    email_ref=trigger,
                ),
            )
            rows.append(row)
            changes.append(f"Added new item '{name}' from email: \"{trigger}\"")

        if changes:
            logger.info(f"EmailOverride: {len(changes)} change(s) applied")
        return rows, changes

    def _call_llm(self, email_text: str, items_text: str) -> Dict:
        try:
            prompt = _PROMPT.format(
                email_text=email_text[:3000],
                trim_items=items_text[:4000],
            )
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=1,
            )
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"EmailOverride LLM error: {e}")
            return {}

    @staticmethod
    def _index_by_name(items: list, key: str) -> Dict[str, Dict]:
        return {
            (it.get(key) or "").lower().strip(): it
            for it in items
            if isinstance(it, dict)
        }
