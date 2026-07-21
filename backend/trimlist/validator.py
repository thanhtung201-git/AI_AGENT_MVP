"""
validator.py — Step 5: Validate Trimlist and generate Alert List.

Checks each TrimRow for:
  - Missing material code      → alert: missing_code
  - Missing supplier           → alert: missing_supplier
  - Missing placement          → alert: missing_placement
  - Missing color              → alert: missing_color
  - Missing consumption        → alert: missing_consumption
  - Missing remark             → alert: missing_remark (warning only)
  - Duplicate trim item        → alert: duplicate
  - Unknown category           → alert: unknown_category
  - No source traceability     → alert: no_source

Severity levels:
  ERROR   — must be resolved before submission
  WARNING — should be checked, but not blocking
  INFO    — informational only
"""
import logging
from typing import Dict, List, Tuple

from backend.trimlist.traceability import TrimRow, CATEGORY_ORDER

logger = logging.getLogger(__name__)

# Fields that are REQUIRED (ERROR if missing)
_REQUIRED_FIELDS = {
    "material_name": "Material name is empty",
    "category":      "Category is not classified",
}

# Fields that generate WARNING if missing
_RECOMMENDED_FIELDS = {
    "material_code": "No material code — cannot be used for ERP ordering",
    "supplier":      "No supplier — sourcing incomplete",
    "placement":     "No placement — cannot confirm usage",
    "color":         "No color specification",
}

# Fields that generate INFO if missing
_OPTIONAL_FIELDS = {
    "consumption": "No consumption per garment",
    "remark":      "No remark",
}


class Alert:
    def __init__(self, severity: str, item_name: str, code: str, message: str):
        self.severity  = severity   # ERROR | WARNING | INFO
        self.item_name = item_name
        self.code      = code
        self.message   = message

    def to_dict(self) -> Dict:
        return {
            "severity":  self.severity,
            "item_name": self.item_name,
            "code":      self.code,
            "message":   self.message,
        }


class TrimlistValidator:
    """Validates TrimRow list and attaches alerts to each row + global alert list."""

    def validate(self, rows: List[TrimRow]) -> Tuple[List[TrimRow], List[Alert]]:
        """
        Validate all rows.

        Returns:
            (rows_with_alerts_attached, global_alert_list)
        """
        global_alerts: List[Alert] = []
        seen_names: Dict[tuple, int] = {}

        for row in rows:
            name = row.material_name or "(unnamed)"

            # Keep every alert the earlier phases raised — Tech Pack ↔ Trim Master
            # conflicts, "only for garment-dye orders" conditions, recovered rows,
            # which seasonal code was chosen. Only the field checks below are the
            # validator's own to regenerate; wiping the rest hides the findings the
            # user most needs.
            upstream = list(row.alerts or [])
            row.alerts = list(upstream)
            for a in upstream:
                head, _, rest = a.partition(":")
                sev = head.strip().upper()
                if sev == "CONFLICT":
                    global_alerts.append(Alert("WARNING", name, "conflict", rest.strip()))
                elif sev in ("ERROR", "WARNING", "INFO"):
                    global_alerts.append(Alert(sev, name, "review", rest.strip()))
                else:
                    global_alerts.append(Alert("WARNING", name, "review", a))

            # ── Required fields (ERROR) ──────────────────────────────────────
            for field, msg in _REQUIRED_FIELDS.items():
                val = getattr(row, field, None)
                if not val or str(val).strip() in ("", "OTHER"):
                    alert = Alert("ERROR", name, f"missing_{field}", msg)
                    row.alerts.append(f"ERROR: {msg}")
                    global_alerts.append(alert)

            # ── Recommended fields (WARNING) ─────────────────────────────────
            for field, msg in _RECOMMENDED_FIELDS.items():
                val = getattr(row, field, None)
                if not val or str(val).strip() == "":
                    alert = Alert("WARNING", name, f"missing_{field}", msg)
                    row.alerts.append(f"WARNING: {msg}")
                    global_alerts.append(alert)

            # ── Optional fields (INFO) ────────────────────────────────────────
            for field, msg in _OPTIONAL_FIELDS.items():
                val = getattr(row, field, None)
                if not val or str(val).strip() == "":
                    alert = Alert("INFO", name, f"missing_{field}", msg)
                    global_alerts.append(alert)

            # ── Duplicate check ───────────────────────────────────────────────
            # Only flag as duplicate when ALL 3 match: name + code + placement
            # Same name with different placement = DIFFERENT rows (e.g. 5 interlinings)
            dup_key = (
                name.lower().strip(),
                (row.material_code or "").lower().strip(),
                (row.placement or "").lower().strip(),
            )
            if dup_key in seen_names:
                alert = Alert(
                    "WARNING", name, "duplicate",
                    f"True duplicate (same name + code + placement) — also at row {seen_names[dup_key]}",
                )
                row.alerts.append(f"WARNING: Duplicate — row {seen_names[dup_key]}")
                global_alerts.append(alert)
            else:
                seen_names[dup_key] = rows.index(row) + 1

            # ── Source traceability check ─────────────────────────────────────
            src = row.source
            if not src.techpack_ref and not src.master_ref and not src.email_ref:
                alert = Alert("INFO", name, "no_source", "No source traceability — origin unknown")
                global_alerts.append(alert)

        # ── Code-reuse check ─────────────────────────────────────────────────
        # A single material code attached to two DIFFERENT materials is almost
        # always a bad Trim Master match (e.g. code 8960 wrongly put on both
        # Butterfly and Polybag). Flag every row that shares a code with an
        # unrelated material so the user can correct it.
        self._flag_code_reuse(rows, global_alerts)

        # Sort rows: by category order, then by name
        rows.sort(key=lambda r: (CATEGORY_ORDER.get(r.category, 99), r.material_name.lower()))

        errors   = sum(1 for a in global_alerts if a.severity == "ERROR")
        warnings = sum(1 for a in global_alerts if a.severity == "WARNING")
        logger.info(
            f"Validator: {len(rows)} rows — {errors} errors, {warnings} warnings, "
            f"{len(global_alerts) - errors - warnings} info"
        )

        return rows, global_alerts

    @staticmethod
    def _norm_name(s: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    def _flag_code_reuse(self, rows: List[TrimRow], global_alerts: List[Alert]) -> None:
        by_code: Dict[str, List[TrimRow]] = {}
        for row in rows:
            code = (row.material_code or "").strip()
            if code:
                by_code.setdefault(code, []).append(row)

        for code, shared in by_code.items():
            distinct_names = {self._norm_name(r.material_name) for r in shared}
            if len(distinct_names) <= 1:
                continue  # same material split by placement — legitimate
            names = ", ".join(sorted({r.material_name for r in shared}))
            for row in shared:
                msg = f"Mã '{code}' gán cho nhiều vật liệu khác nhau ({names}) — khả năng khớp sai Trim Master"
                row.alerts.append(f"WARNING: {msg}")
                global_alerts.append(Alert("WARNING", row.material_name, "code_reuse", msg))

    def summary(self, alerts: List[Alert]) -> Dict:
        return {
            "total":    len(alerts),
            "errors":   sum(1 for a in alerts if a.severity == "ERROR"),
            "warnings": sum(1 for a in alerts if a.severity == "WARNING"),
            "infos":    sum(1 for a in alerts if a.severity == "INFO"),
            "by_code":  self._count_by_code(alerts),
        }

    @staticmethod
    def _count_by_code(alerts: List[Alert]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for a in alerts:
            counts[a.code] = counts.get(a.code, 0) + 1
        return counts
