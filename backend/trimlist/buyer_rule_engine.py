"""
buyer_rule_engine.py — Step 3: Apply Buyer Rules from configurable JSON.

Rules are loaded from:
  config/buyer_rules/{BUYER_CODE}.json   (buyer-specific)
  config/buyer_rules/default.json        (applies to all buyers)

The LLM reads the rules and applies them semantically to each trim item.

NO hardcoded logic in Python. All business rules live in JSON config files.
New buyers → add a new JSON file. Zero code changes needed.

Rule JSON structure:
{
  "buyer_code": "HAZZYS",
  "version": "1.0",
  "rules": [
    {
      "id": "HAZZYS-001",
      "name": "DTM Sewing Thread",
      "description": "All sewing thread must be DTM (Dye To Match) main fabric color",
      "applies_to": {
        "category": "THREAD & BUTTON",
        "name_contains": ["thread", "sewing"]
      },
      "action": {
        "set_color": "DTM",
        "append_remark": "Thread color to match main fabric — DTM"
      }
    }
  ]
}
"""
import json
import logging
import os
from typing import Dict, List, Optional

from backend.trimlist.traceability import TrimRow
from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "buyer_rules",
)

_SYSTEM = """You are a garment merchandising specialist applying buyer-specific business rules.
Return valid JSON only. No markdown, no explanation."""

_PROMPT = """
Apply the following BUYER RULES to each item in the TRIM LIST.

BUYER: {buyer_code}

BUYER RULES:
{rules_text}

TRIM LIST (JSON):
{trim_items}

INSTRUCTIONS:
1. Read each rule carefully.
2. For each trim item, check if any rule applies (by category, name, or type).
3. If a rule applies: map the rule's action to modifications using this mapping:
   - action "set_color"          → modifications.color
   - action "append_remark"      → modifications.remark
   - action "set_consumption"    → modifications.consumption
   - action "preferred_supplier" → modifications.preferred_supplier
   - action "set_supplier"       → modifications.supplier
   - action "set_spec"           → modifications.spec
4. If no rule applies to an item, return empty modifications and rule_applied = null.

RETURN JSON:
{{
  "results": [
    {{
      "material_name":  "Sewing Thread",
      "modifications":  {{
        "color":  "DTM",
        "remark": "Thread color to match main fabric — DTM per Rule HAZZYS-001"
      }},
      "rule_applied":   "HAZZYS-001: DTM Sewing Thread"
    }},
    {{
      "material_name":  "YKK Zipper",
      "modifications":  {{
        "preferred_supplier": "YKK",
        "remark": "Preferred brand: YKK. Alternatives require buyer approval."
      }},
      "rule_applied":   "HAZZYS-003: YKK Zipper Preferred"
    }},
    {{
      "material_name":  "Polybag",
      "modifications":  {{
        "consumption": "1 PCS",
        "remark": "Individual polybag — 1 pc per garment"
      }},
      "rule_applied":   "HAZZYS-005: Individual Polybag Required"
    }},
    {{
      "material_name":  "Main Label",
      "modifications":  {{}},
      "rule_applied":   null
    }}
  ]
}}

IMPORTANT:
- Only modify fields explicitly targeted by the rule action.
- Never invent material codes, supplier codes, or quantities.
- If a field modification would remove existing data, skip it.
- All items in the trim list must appear in results (even if no rule applies).
"""


class BuyerRuleEngine:
    """
    Loads buyer rules from JSON config and applies them to TrimRow list using LLM.
    """

    def __init__(self):
        self.llm = GroqClient()

    def apply(self, rows: List[TrimRow], buyer_code: str) -> List[TrimRow]:
        """
        Apply buyer rules to all rows.

        Args:
            rows:       List[TrimRow] after Trim Master mapping
            buyer_code: e.g. "HAZZYS", "UNIQLO" — used to load correct rule file

        Returns:
            Same rows, with modifications applied in-place.
        """
        if not rows:
            return rows

        rules = self._load_rules(buyer_code)
        if not rules:
            logger.info(f"BuyerRuleEngine: no rules found for buyer '{buyer_code}'")
            return rows

        rules_text  = json.dumps(rules, ensure_ascii=False, indent=2)
        items_text  = json.dumps([r.to_dict() for r in rows], ensure_ascii=False)
        results     = self._call_llm(buyer_code, rules_text, items_text)
        result_index = self._index_results(results)

        applied = 0
        for row in rows:
            r = result_index.get(row.material_name.lower().strip())
            if not r:
                continue
            mods = r.get("modifications") or {}
            rule_applied = r.get("rule_applied")
            if not mods and not rule_applied:
                continue

            # color: buyer rule OVERRIDES (buyer standard takes priority)
            if mods.get("color"):
                row.color = mods["color"]

            # remark: APPEND (accumulate from all sources)
            if mods.get("remark"):
                row.remark = (row.remark + " | " + mods["remark"]) if row.remark else mods["remark"]

            # spec: only fill if empty
            if mods.get("spec") and not row.spec:
                row.spec = mods["spec"]

            # placement: only fill if empty
            if mods.get("placement") and not row.placement:
                row.placement = mods["placement"]

            # consumption: set if specified by rule (e.g. polybag = 1 pc/garment)
            if mods.get("consumption") and not row.consumption:
                row.consumption = mods["consumption"]

            # supplier: preferred_supplier sets supplier if not already confirmed
            if mods.get("preferred_supplier") and not row.supplier:
                row.supplier = mods["preferred_supplier"]
            elif mods.get("supplier") and not row.supplier:
                row.supplier = mods["supplier"]

            if rule_applied:
                row.source.buyer_rule = rule_applied
                applied += 1

        logger.info(f"BuyerRuleEngine: {applied}/{len(rows)} items modified by buyer rules")
        return rows

    def _load_rules(self, buyer_code: str) -> List[Dict]:
        """Load rules from default.json + {BUYER_CODE}.json, merged."""
        rules: List[Dict] = []

        # 1. Default rules (applies to all buyers)
        default_path = os.path.join(_CONFIG_DIR, "default.json")
        if os.path.exists(default_path):
            try:
                with open(default_path, encoding="utf-8") as f:
                    data = json.load(f)
                    rules.extend(data.get("rules") or [])
            except Exception as e:
                logger.warning(f"BuyerRuleEngine: cannot load default.json — {e}")

        # 2. Buyer-specific rules
        if buyer_code:
            buyer_path = os.path.join(_CONFIG_DIR, f"{buyer_code.upper()}.json")
            if os.path.exists(buyer_path):
                try:
                    with open(buyer_path, encoding="utf-8") as f:
                        data = json.load(f)
                        rules.extend(data.get("rules") or [])
                    logger.info(f"BuyerRuleEngine: loaded {buyer_path}")
                except Exception as e:
                    logger.warning(f"BuyerRuleEngine: cannot load {buyer_path} — {e}")

        return rules

    def _call_llm(self, buyer_code: str, rules_text: str, items_text: str) -> list:
        try:
            prompt = _PROMPT.format(
                buyer_code=buyer_code,
                rules_text=rules_text,
                trim_items=items_text[:5000],
            )
            result = self.llm.extract_json_with_retry(
                system_prompt=_SYSTEM,
                user_content=prompt,
                max_retries=1,
            )
            return result.get("results") or []
        except Exception as e:
            logger.error(f"BuyerRuleEngine LLM error: {e}")
            return []

    def _index_results(self, results: list) -> Dict[str, Dict]:
        return {
            (r.get("material_name") or "").lower().strip(): r
            for r in results
            if isinstance(r, dict)
        }
