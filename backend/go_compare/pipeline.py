"""
pipeline.py — Orchestrates the PO ↔ GO workflow as TWO sequential steps.

STEP 1  generate_batch_go(po):
  1. DocumentReader   — LLM reads PO → CanonicalOrder (PO)
  2. BatchGOGenerator — deterministic → Batch_GO_Output.xlsx
  3. persist PO canonical to disk (so step 2 needs no re-read)

STEP 2  run_compare(token, go?):
  4. DocumentReader   — LLM reads GO (uploaded real GO, else the generated Batch GO)
  5. CompareEngine    — PO canonical vs GO canonical → rows + alerts
  6. ReportWriter     — Compare_Report.xlsx + Alerts.json

run() is kept as a one-shot convenience (used by scripts/tests) that chains both.

Python = orchestration/validation/export. LLM = understanding/extraction/mapping.
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "sample_data/go_compare"


def _po_json_path(out_dir: str, token: str) -> str:
    return os.path.join(out_dir, f"PO_canonical_{token}.json")


def _batch_go_path(out_dir: str, token: str) -> str:
    return os.path.join(out_dir, f"Batch_GO_Output_{token}.xlsx")


class GOComparePipeline:

    # ── STEP 1 ────────────────────────────────────────────────────────────────

    def generate_batch_go(
        self,
        po_file_path: str,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read PO → generate Batch GO → persist PO canonical. No comparison here."""
        out_dir = output_dir or DEFAULT_OUTPUT_DIR
        os.makedirs(out_dir, exist_ok=True)
        token = datetime.now().strftime("%Y%m%d_%H%M%S")

        from backend.go_compare.document_reader import DocumentReader
        from backend.go_compare.batch_go_generator import BatchGOGenerator

        logger.info("GOCompare STEP 1a: read PO")
        try:
            po_order = DocumentReader().read(po_file_path, "PO", "PO")
            if not po_order.lines:
                return {"success": False, "error": "Không trích xuất được order line nào từ PO"}
        except Exception as e:
            return {"success": False, "error": f"Đọc PO thất bại: {e}"}

        # Validate BEFORE generating GO — never silently emit an incorrect GO.
        from backend.go_compare.po_parser.validator import POValidator, ValidationIssue, WARNING
        from backend.go_compare.template_writer import find_missing_mandatory
        validator = POValidator()
        issues = validator.validate(po_order)

        # A mandatory Batch GO field the PO gave no data for is not a crash — the file
        # still generates — but the end user must be told, or they upload a file the
        # ERP rejects and only find out from the buyer.
        for m in find_missing_mandatory(po_order):
            issues.append(ValidationIssue(
                WARNING, "missing_mandatory",
                f"Thiếu dữ liệu input cho trường bắt buộc "
                f"'{m['field']}' ({m['sheet']} · {m['section']}) — end user cần bổ sung",
            ))

        val_summary = POValidator.summary(issues)
        logger.info(f"GOCompare STEP 1 validation: {val_summary}")

        logger.info("GOCompare STEP 1b: generate Batch GO")
        try:
            batch_go_path = _batch_go_path(out_dir, token)
            BatchGOGenerator().generate(po_order, batch_go_path)
        except Exception as e:
            return {"success": False, "error": f"Tạo Batch GO thất bại: {e}"}

        # persist PO canonical so STEP 2 does not re-read/re-pay the LLM
        try:
            with open(_po_json_path(out_dir, token), "w", encoding="utf-8") as f:
                json.dump(po_order.to_dict(), f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"GOCompare: could not persist PO canonical: {e}")

        return {
            "success":       True,
            "token":         token,
            "po":            po_order.to_dict(),
            "batch_go_path": batch_go_path,
            "validation":    {"summary": val_summary, "issues": [i.to_dict() for i in issues]},
            "error":         None,
        }

    # ── STEP 2 ────────────────────────────────────────────────────────────────

    def run_compare(
        self,
        token: str,
        output_dir: Optional[str] = None,
        go_file_path: Optional[str] = None,
        qty_tolerance_pct: float = 0.0,
    ) -> Dict[str, Any]:
        """Compare the PO (from STEP 1) against a GO (uploaded real GO, else the
        generated Batch GO round-trip)."""
        out_dir = output_dir or DEFAULT_OUTPUT_DIR

        from backend.go_compare.canonical import order_from_llm
        from backend.go_compare.document_reader import DocumentReader
        from backend.go_compare.compare_engine import CompareEngine
        from backend.go_compare.report_writer import ReportWriter

        # Load PO canonical from STEP 1
        po_json = _po_json_path(out_dir, token)
        if not os.path.exists(po_json):
            return {"success": False, "error": "Không tìm thấy dữ liệu PO của bước 1 (token không hợp lệ)"}
        try:
            with open(po_json, "r", encoding="utf-8") as f:
                po_order = order_from_llm(json.load(f), "PO", "PO")
        except Exception as e:
            return {"success": False, "error": f"Không đọc được PO canonical: {e}"}

        batch_go_path = _batch_go_path(out_dir, token)
        go_is_real    = bool(go_file_path and os.path.exists(go_file_path))
        go_read_path  = go_file_path if go_is_real else batch_go_path

        logger.info(f"GOCompare STEP 2a: read GO ({'real upload' if go_is_real else 'generated round-trip'})")
        try:
            go_order = DocumentReader().read(go_read_path, "GO", "GO Information")
        except Exception as e:
            return {"success": False, "error": f"Đọc GO thất bại: {e}"}

        logger.info("GOCompare STEP 2b: compare")
        compare = CompareEngine(qty_tolerance_pct=qty_tolerance_pct).compare(po_order, go_order)

        logger.info("GOCompare STEP 2c: write reports")
        try:
            report_path = os.path.join(out_dir, f"Compare_Report_{token}.xlsx")
            alerts_path = os.path.join(out_dir, f"Alerts_{token}.json")
            rw = ReportWriter()
            rw.write_compare_report(compare, report_path)
            rw.write_alerts_json(compare, alerts_path)
        except Exception as e:
            return {"success": False, "error": f"Ghi báo cáo thất bại: {e}"}

        return {
            "success":       True,
            "token":         token,
            "go_source":     "uploaded" if go_is_real else "generated",
            "po":            po_order.to_dict(),
            "go":            go_order.to_dict(),
            "compare":       compare,
            "batch_go_path": batch_go_path,
            "report_path":   report_path,
            "alerts_path":   alerts_path,
            "error":         None,
        }

    # ── One-shot convenience (scripts/tests) ──────────────────────────────────

    def run(
        self,
        po_file_path: str,
        go_file_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        qty_tolerance_pct: float = 0.0,
    ) -> Dict[str, Any]:
        gen = self.generate_batch_go(po_file_path, output_dir)
        if not gen.get("success"):
            return gen
        cmp = self.run_compare(gen["token"], output_dir, go_file_path, qty_tolerance_pct)
        if not cmp.get("success"):
            return cmp
        cmp["batch_go_path"] = gen["batch_go_path"]
        return cmp
