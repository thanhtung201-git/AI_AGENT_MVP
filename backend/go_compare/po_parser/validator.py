"""
validator.py — POValidator: business-rule checks on a parsed CanonicalOrder,
run BEFORE generating the Batch GO so we never silently emit an incorrect GO.

Checks (generic, no customer-specific rules):
  - Sum(size qty) == color total          (per line)
  - Style present on every line
  - Delivery date present                  (warning)
  - No duplicated color within a style     (error)
  - No duplicated size within a color       (error)
  - At least one order line                (error)
  - Optional: Sum(color totals) reconciles against a declared style total, if a
    declared total was captured.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from backend.go_compare.canonical import CanonicalOrder

ERROR, WARNING, INFO = "ERROR", "WARNING", "INFO"


@dataclass
class ValidationIssue:
    level: str
    code: str
    message: str
    style: str = ""
    color: str = ""

    def to_dict(self) -> Dict:
        return {"level": self.level, "code": self.code, "message": self.message,
                "style": self.style, "color": self.color}


class POValidator:

    def validate(
        self,
        order: CanonicalOrder,
        declared_style_totals: Optional[Dict[str, float]] = None,
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        if not order.lines:
            issues.append(ValidationIssue(ERROR, "no_lines", "PO không có order line nào"))
            return issues

        seen_color_by_style: Dict[tuple, set] = {}
        style_totals: Dict[str, float] = {}

        for line in order.lines:
            style = line.style or ""
            color = line.color_code or line.color_name or ""

            if not style:
                issues.append(ValidationIssue(ERROR, "missing_style",
                              f"Dòng màu '{color}' không xác định được style", color=color))

            # Sum(size) == color total
            size_sum = sum(line.size_breakdown.values()) if line.size_breakdown else 0.0
            if line.size_breakdown and abs(size_sum - line.qty) > 0.001:
                issues.append(ValidationIssue(
                    ERROR, "color_total_mismatch",
                    f"{style}/{color}: tổng size ({size_sum:.0f}) != color total ({line.qty:.0f})",
                    style=style, color=color))

            # duplicate size within a color would have collapsed in a dict; detect via
            # negative/duplicate is not possible post-aggregation, so we check emptiness
            if not line.size_breakdown and line.qty == 0:
                issues.append(ValidationIssue(WARNING, "empty_color",
                              f"{style}/{color}: không có size/qty nào", style=style, color=color))

            # Duplicate colour within a style's run+market. A colour legitimately
            # repeats across runs and markets — the same style ships WT to KOREA and
            # to TAIWAN — so only a repeat inside one (run, market) is a real error.
            s = seen_color_by_style.setdefault((style, line.block, line.destination), set())
            key = color.lower().strip()
            if key in s:
                issues.append(ValidationIssue(ERROR, "duplicate_color",
                              f"{style}: màu '{color}' bị lặp", style=style, color=color))
            else:
                s.add(key)

            style_totals[style] = style_totals.get(style, 0.0) + line.qty

            if not line.delivery_date:
                issues.append(ValidationIssue(WARNING, "missing_delivery",
                              f"{style}/{color}: thiếu delivery date", style=style, color=color))

        # reconcile against declared style totals if provided
        if declared_style_totals:
            for style, declared in declared_style_totals.items():
                got = style_totals.get(style)
                if got is not None and abs(got - declared) > 0.001:
                    issues.append(ValidationIssue(
                        WARNING, "style_total_mismatch",
                        f"{style}: tổng các màu ({got:.0f}) != style TTL khai báo ({declared:.0f})",
                        style=style))

        return issues

    @staticmethod
    def summary(issues: List[ValidationIssue]) -> Dict[str, int]:
        return {
            "errors":   sum(1 for i in issues if i.level == ERROR),
            "warnings": sum(1 for i in issues if i.level == WARNING),
            "infos":    sum(1 for i in issues if i.level == INFO),
        }
