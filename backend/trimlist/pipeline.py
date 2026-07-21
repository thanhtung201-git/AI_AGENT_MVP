"""
pipeline.py — Trimlist Generation Pipeline (v3 — LLM-driven architecture)

Full pipeline:
  Phase 1  DocumentAnalyzer    — Semantic document mapping (sections, colorways, style info)
  Phase 2  MaterialExtractor   — Extract ALL fields from BOM + cross-reference full doc
  Phase 3  MasterIntegrator    — LLM-merge Tech Pack + Trim Master, report conflicts
  Phase 4  BuyerRuleEngine     — Apply buyer-specific rules from JSON config
  Phase 5  EmailOverride       — Apply email / note overrides
  Phase 6  TrimlistValidator   — Validate completeness, detect duplicates
  Phase 7  Self-check          — 6-point quality report
  Phase 8  TrimlistExcelWriter — Export Excel (3 sheets)

Zero hardcoded:
  - page numbers
  - company names
  - column indices
  - sheet names
  - document-specific keywords
  - regex for one document

Every decision is LLM-driven semantic reasoning.
"""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OUTPUT_DIR = "sample_data/trimlist"
os.makedirs(OUTPUT_DIR, exist_ok=True)


class TrimlistPipeline:
    """Orchestrates the full LLM-driven Trimlist generation pipeline."""

    def run(
        self,
        techpack_path: str,
        master_trim_path: Optional[str] = None,
        email_note: str = "",
        buyer_code: str = "",
        garment_type: str = "",
        branch: str = "",
        branch_confirmed: bool = False,
        meta: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full pipeline.

        Returns:
        {
          "success":        bool,
          "items":          List[dict],
          "item_count":     int,
          "bom_line_count": int | None,
          "alert_summary":  dict,
          "alerts":         List[dict],
          "email_changes":  List[str],
          "self_check":     List[str],
          "excel_path":     str,
          "excel_token":    str,
          "steps":          dict,
          "error":          str | None,
        }
        """
        meta  = meta or {}
        steps = {}

        # ── Read raw text ──────────────────────────────────────────────────────
        logger.info("Pipeline: reading Tech Pack file")
        raw_text = self._read_file(techpack_path)
        if not raw_text:
            return {"success": False, "error": "Không đọc được nội dung Tech Pack"}

        # ── Phase 1: Semantic Document Analysis ───────────────────────────────
        logger.info("Pipeline Phase 1: DocumentAnalyzer")
        try:
            from backend.trimlist.document_analyzer import DocumentAnalyzer
            doc_map = DocumentAnalyzer().analyze(raw_text)
            steps["phase1_analyze"] = {
                "status":       "ok",
                "sections":     len(doc_map.get("sections") or []),
                "bom_sections": len(doc_map.get("bom_sections") or []),
                "colorways":    doc_map.get("colorways") or [],
            }
        except Exception as e:
            return {"success": False, "error": f"Phase 1 (Document Analysis) failed: {e}"}

        bom_line_count = doc_map.get("bom_total_lines") or 0
        style_info     = doc_map.get("style_info") or {}

        # ── Phase 1.2: Branch detection (gender × construction) ────────────────
        # Step 1 of the manual process: read the Tech Pack to know the branch, which
        # decides WHICH Trim Master sheet to use. A user-confirmed `branch` wins;
        # otherwise we auto-detect and report confidence for a 1-click confirm.
        logger.info("Pipeline Phase 1.2: BranchDetector")
        try:
            from backend.trimlist.branch_detector import BranchDetector
            branch_info = BranchDetector().detect(raw_text, style_info)
        except Exception as e:
            logger.warning(f"Phase 1.2 error (non-fatal): {e}")
            branch_info = {"branch_key": None, "confidence": "low", "gender": None,
                           "construction": None, "evidence": {}, "source": "error"}
        effective_branch = branch or branch_info.get("branch_key") or garment_type
        branch_info["used"] = effective_branch
        # Only a branch the USER actually picked counts as confirmed. The UI
        # pre-fills the dropdown with this same detector's guess and posts it back,
        # so a non-empty `branch` alone proves nothing.
        branch_info["confirmed"] = bool(branch and branch_confirmed)
        steps["phase1_2_branch"] = {"status": "ok", "branch": effective_branch,
                                    "confidence": branch_info.get("confidence")}

        # ── Phase 1.5: Verbatim raw-line transcription (anti-miss ground truth) ─
        logger.info("Pipeline Phase 1.5: RawLineExtractor")
        raw_lines: List[str] = []
        try:
            from backend.trimlist.raw_line_extractor import RawLineExtractor
            raw_result = RawLineExtractor().extract(doc_map.get("bom_sections") or [])
            raw_lines  = raw_result.get("raw_lines") or []
            steps["phase1_5_raw"] = {"status": "ok", "raw_lines": len(raw_lines)}
        except Exception as e:
            logger.warning(f"Phase 1.5 error (non-fatal): {e}")
            steps["phase1_5_raw"] = {"status": "error", "error": str(e)}

        # ── Phase 2: Material Extraction with Cross-Reference ─────────────────
        logger.info("Pipeline Phase 2: MaterialExtractor")
        try:
            from backend.trimlist.material_extractor import MaterialExtractor
            canonical_items = MaterialExtractor().extract(doc_map)
            steps["phase2_extract"] = {
                "status":     "ok",
                "item_count": len(canonical_items),
            }
            if not canonical_items:
                return {"success": False, "error": "Không tìm thấy trim items trong Tech Pack"}
        except Exception as e:
            return {"success": False, "error": f"Phase 2 (Material Extraction) failed: {e}"}

        # ── Phase 3: Trim Master Integration (branch-scoped) ──────────────────
        logger.info("Pipeline Phase 3: MasterIntegrator")
        master_items     = []
        master_sheet     = ""
        master_exceptions = {"styles": [], "reminders": []}
        if master_trim_path and os.path.exists(master_trim_path):
            try:
                from backend.extractors.master_trim_reader import MasterTrimReader
                reader = MasterTrimReader(master_trim_path)
                # Deterministic branch vote: the Tech Pack quotes real material codes,
                # and each master sheet carries its branch's codes. Hard evidence from
                # the files beats a keyword/LLM guess — but never a user-confirmed branch.
                if not branch_info["confirmed"]:
                    vote = reader.detect_branch_by_codes(raw_text)
                    if vote.get("branch") and vote["branch"] != effective_branch:
                        logger.info(
                            f"Phase 3: branch vote overrides '{effective_branch}' → "
                            f"'{vote['branch']}' (codes matched: {vote['scores']})"
                        )
                        effective_branch = vote["branch"]
                        branch_info["used"] = effective_branch
                        branch_info["source"] = "code_overlap"
                        branch_info["evidence"]["codes"] = vote["scores"]
                        steps["phase1_2_branch"]["branch"] = effective_branch
                        steps["phase1_2_branch"]["vote"] = vote["scores"]
                master_result     = reader.read_branch(effective_branch)
                master_items      = master_result.get("items") or []
                master_sheet      = master_result.get("base_sheet") or ""
                master_exceptions = master_result.get("exceptions") or master_exceptions
                logger.info(f"Trim Master (branch '{effective_branch}'): {len(master_items)} "
                            f"items from '{master_sheet}', exception sheet="
                            f"{master_result.get('exception_sheet')}")
            except Exception as e:
                logger.warning(f"Phase 3: Trim Master read error (non-fatal): {e}")

        try:
            from backend.trimlist.master_integrator import MasterIntegrator
            merged_items = MasterIntegrator().merge(canonical_items, master_items, master_sheet)
            matched = sum(1 for m in merged_items if m.get("confidence") not in (None, "none"))
            steps["phase3_integrate"] = {
                "status":        "ok",
                "master_items":  len(master_items),
                "matched":       matched,
                "total":         len(merged_items),
            }
        except Exception as e:
            logger.warning(f"Phase 3 error (non-fatal): {e}")
            merged_items = canonical_items
            steps["phase3_integrate"] = {"status": "error", "error": str(e)}

        # ── Phase 3.4: Attach exact Master cell to items that borrowed a Master code ─
        # A Tech Pack item enriched with a Master code (via the LLM merge) has no source
        # cell → its "Primary Source" can't deep-link. Match its code back to the Master
        # row (which carries _loc) deterministically so the link works too.
        import re as _re
        _codeloc = {
            _re.sub(r"[^a-z0-9]", "", (m.get("supplier_code") or "").lower()): m.get("_loc")
            for m in master_items if m.get("supplier_code") and m.get("_loc")
        }
        if _codeloc:
            attached = 0
            for it in merged_items:
                if not it.get("_loc"):
                    c = _re.sub(r"[^a-z0-9]", "", (it.get("material_code") or "").lower())
                    if c and _codeloc.get(c):
                        it["_loc"] = _codeloc[c]
                        attached += 1
            logger.info(f"Phase 3.4: attached Master cell to {attached} merged item(s)")

        # ── Phase 3.5: Add the branch's packing/label items (deterministic) ────
        # Take the WHOLE branch list, apply style exceptions + measurement flags,
        # dedup against the Tech Pack by fixed key. No LLM "which are standard".
        logger.info("Pipeline Phase 3.5: BranchTrimResolver")
        if master_items:
            try:
                from backend.trimlist.branch_trim_resolver import BranchTrimResolver
                resolved = BranchTrimResolver().resolve(
                    master_items=master_items,
                    exceptions=master_exceptions,
                    techpack_items=merged_items,
                    style_code=(meta.get("style_code") or style_info.get("style_code") or ""),
                    season=(meta.get("season") or style_info.get("season") or ""),
                )
                packing_extras = resolved.get("items") or []
                if packing_extras:
                    merged_items = merged_items + packing_extras
                steps["phase3_5_packing"] = {"status": "ok", **resolved.get("report", {})}
            except Exception as e:
                logger.warning(f"Phase 3.5 error (non-fatal): {e}")
                steps["phase3_5_packing"] = {"status": "error", "error": str(e)}
        else:
            steps["phase3_5_packing"] = {"status": "skipped", "reason": "No Trim Master"}

        # ── Convert to TrimRow ─────────────────────────────────────────────────
        from backend.trimlist.canonical_to_trimrow import canonical_to_trimrows
        rows = canonical_to_trimrows(merged_items)

        if not rows:
            return {"success": False, "error": "Không chuyển đổi được canonical items sang TrimRow"}

        # ── Normalize: clean LLM artifacts (color in consumption, wrong unit, etc.)
        try:
            from backend.trimlist.normalizer import TrimNormalizer
            rows = TrimNormalizer().normalize(rows)
        except Exception as e:
            logger.warning(f"Normalize error (non-fatal): {e}")

        # ── Phase 4: Buyer Rules ───────────────────────────────────────────────
        logger.info("Pipeline Phase 4: BuyerRuleEngine")
        if buyer_code:
            try:
                from backend.trimlist.buyer_rule_engine import BuyerRuleEngine
                rows = BuyerRuleEngine().apply(rows, buyer_code)
                applied = sum(1 for r in rows if r.source.buyer_rule)
                steps["phase4_rules"] = {"status": "ok", "applied": applied}
            except Exception as e:
                logger.warning(f"Phase 4 error (non-fatal): {e}")
                steps["phase4_rules"] = {"status": "error", "error": str(e)}
        else:
            steps["phase4_rules"] = {"status": "skipped", "reason": "No buyer_code"}

        # ── Phase 5: Email Overrides ───────────────────────────────────────────
        logger.info("Pipeline Phase 5: EmailOverride")
        email_changes: List[str] = []
        if email_note and email_note.strip():
            try:
                from backend.trimlist.email_override import EmailOverride
                rows, email_changes = EmailOverride().apply(rows, email_note)
                steps["phase5_email"] = {"status": "ok", "changes": len(email_changes)}
            except Exception as e:
                logger.warning(f"Phase 5 error (non-fatal): {e}")
                steps["phase5_email"] = {"status": "error", "error": str(e)}
        else:
            steps["phase5_email"] = {"status": "skipped", "reason": "No email note"}

        # ── Phase 5.5: Reverse reconciliation vs raw lines (recover misses) ────
        logger.info("Pipeline Phase 5.5: Reconciliation")
        recon_report: Dict[str, Any] = {}
        if raw_lines:
            try:
                from backend.trimlist.reconciliation import reconcile
                rows, recon_report = reconcile(rows, raw_lines)
                steps["phase5_5_reconcile"] = {"status": "ok", **recon_report}
            except Exception as e:
                logger.warning(f"Phase 5.5 error (non-fatal): {e}")
                steps["phase5_5_reconcile"] = {"status": "error", "error": str(e)}
        else:
            steps["phase5_5_reconcile"] = {"status": "skipped", "reason": "No raw lines"}

        # ── Phase 5.55: Deterministic code sweep (LLM-free anti-miss net) ─────
        # Every material-code token in the BOM text must land in some row. Codes
        # both LLM passes missed (a wrapped-name hangtag…) are rebuilt from the
        # physical line that carries them.
        try:
            from backend.trimlist.reconciliation import sweep_missing_codes
            bom_text = "\n".join(
                s.get("content", "") for s in (doc_map.get("bom_sections") or [])
            )
            rows, swept = sweep_missing_codes(rows, bom_text)
            # The BOM's own "Pls see T/P" points at the spec pages — sweep the WHOLE
            # document for "(#CODE)" callouts so those materials aren't lost.
            from backend.trimlist.reconciliation import sweep_hash_codes
            rows, swept_hash = sweep_hash_codes(rows, raw_text)
            steps["phase5_55_codesweep"] = {
                "status": "ok", "recovered_codes": swept, "recovered_spec_codes": swept_hash,
            }
        except Exception as e:
            logger.warning(f"Phase 5.55 error (non-fatal): {e}")
            steps["phase5_55_codesweep"] = {"status": "error", "error": str(e)}

        # ── Phase 5.6: Cross-source dedup ──────────────────────────────────────
        # One item must appear ONCE no matter how many paths produced it (Tech Pack
        # extract, raw-line recovery, master branch add). Tech Pack wins; the master
        # duplicate donates any field the kept row lacks before being dropped.
        logger.info("Pipeline Phase 5.6: cross-source dedup")
        try:
            from backend.trimlist.reconciliation import dedup_cross_source
            rows, n_deduped = dedup_cross_source(rows)
            steps["phase5_6_dedup"] = {"status": "ok", "dropped": n_deduped}
        except Exception as e:
            logger.warning(f"Phase 5.6 error (non-fatal): {e}")
            steps["phase5_6_dedup"] = {"status": "error", "error": str(e)}

        # ── Phase 5.7: Resolve multi-version code cells ────────────────────────
        # A master cell stacking one code per season must leave with ONE code —
        # the version the Tech Pack itself uses, else the order's season.
        try:
            from backend.trimlist.branch_trim_resolver import resolve_code_versions
            n_resolved = resolve_code_versions(
                rows, (meta.get("season") or style_info.get("season") or ""), raw_text
            )
            steps["phase5_7_codeversion"] = {"status": "ok", "resolved": n_resolved}
        except Exception as e:
            logger.warning(f"Phase 5.7 error (non-fatal): {e}")
            steps["phase5_7_codeversion"] = {"status": "error", "error": str(e)}

        # ── Phase 6: Validation ────────────────────────────────────────────────
        logger.info("Pipeline Phase 6: TrimlistValidator")
        try:
            from backend.trimlist.validator import TrimlistValidator
            validator    = TrimlistValidator()
            rows, alerts = validator.validate(rows)
            alert_summary = validator.summary(alerts)
            steps["phase6_validate"] = {"status": "ok", **alert_summary}
        except Exception as e:
            logger.warning(f"Phase 6 error (non-fatal): {e}")
            alerts, alert_summary = [], {}
            steps["phase6_validate"] = {"status": "error", "error": str(e)}

        # ── Phase 7: Self-check + completion report ───────────────────────────
        logger.info("Pipeline Phase 7: Self-check")
        self_check = self._selfcheck(rows, bom_line_count, email_changes, alerts)
        if recon_report:
            rc = recon_report.get("recovered", 0)
            if rc > 0:
                self_check.append(
                    f"⚠ [RECONCILE] {rc} dòng bị bỏ sót khi dựng bảng đã được thu hồi từ "
                    f"bản chép thô ({recon_report.get('raw_count')} dòng thô). Kiểm tra các dòng 'recovered'."
                )
            else:
                self_check.append(
                    f"✓ [RECONCILE] Mọi dòng thô đều có trong trimlist "
                    f"({recon_report.get('raw_count')} dòng thô đối chiếu đủ)."
                )
        completion = self._build_completion(rows)
        steps["phase7_selfcheck"] = {"status": "ok", "items": len(self_check)}

        # ── Phase 8: Export Excel ──────────────────────────────────────────────
        logger.info("Pipeline Phase 8: TrimlistExcelWriter")
        try:
            export_meta = self._build_export_meta(meta, style_info)
            ts, excel_path = self._export(
                rows, alerts, export_meta, email_changes, self_check,
                master_path=master_trim_path, master_sheet=master_sheet, techpack_path=techpack_path,
            )
            steps["phase8_export"] = {"status": "ok", "path": excel_path}
        except Exception as e:
            return {"success": False, "error": f"Phase 8 (Excel export) failed: {e}"}

        return {
            "success":         True,
            "items":           [r.to_dict() for r in rows],
            "item_count":      len(rows),
            "bom_line_count":  bom_line_count,
            "alert_summary":   alert_summary,
            "alerts":          [a.to_dict() for a in alerts],
            "email_changes":   email_changes,
            "self_check":      self_check,
            "reconciliation":  recon_report,
            "branch":          branch_info,
            "completion":      completion,
            "pending_summary": completion["pending_summary"],
            "excel_path":      excel_path,
            "excel_token":     ts,
            "steps":           steps,
            "error":           None,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _read_file(self, path: str) -> str:
        try:
            from tools.reader import read_file
            result = read_file(path)
            if result.get("success"):
                return result.get("text") or ""
            logger.error(f"read_file failed: {result.get('error')}")
        except Exception as e:
            logger.error(f"_read_file exception: {e}")
        return ""

    def _build_export_meta(self, meta: Dict, style_info: Dict) -> Dict:
        """Merge user-provided meta with LLM-extracted style info."""
        return {
            "po_number":   meta.get("po_number")  or "",
            "style_code":  meta.get("style_code") or style_info.get("style_code") or "",
            "style_name":  meta.get("style_name") or style_info.get("garment_type") or "",
            "buyer":       meta.get("buyer")       or style_info.get("buyer") or "",
            "order_qty":   meta.get("order_qty")   or "",
            "season":      meta.get("season")      or style_info.get("season") or "",
            "factory":     meta.get("factory")     or "",
            "date":        datetime.now().strftime("%d/%m/%Y"),
            "prepared_by": "AI Agent v3",
        }

    def _selfcheck(
        self,
        rows: list,
        bom_line_count: int,
        email_changes: List[str],
        alerts: list,
    ) -> List[str]:
        report: List[str] = []

        # 1. Line count
        if bom_line_count > 0:
            diff = bom_line_count - len(rows)
            if diff > 0:
                report.append(
                    f"⚠ [LINE COUNT] BOM khai báo {bom_line_count} dòng, "
                    f"Trimlist có {len(rows)} → lệch {diff}. Kiểm tra lại."
                )
            elif diff < 0:
                report.append(
                    f"⚠ [LINE COUNT] Trimlist ({len(rows)} dòng) nhiều hơn BOM ({bom_line_count}). "
                    f"Có thể do tách placement."
                )
            else:
                report.append(f"✓ [LINE COUNT] Số dòng khớp: {len(rows)} dòng.")
        else:
            report.append(f"ℹ [LINE COUNT] Không xác định được tổng BOM. Trimlist: {len(rows)} dòng.")

        # 2. Source coverage
        master_only = [r for r in rows if r.source.master_ref and not r.source.techpack_ref]
        if master_only:
            names = ", ".join(r.material_name for r in master_only[:5])
            report.append(f"⚠ [SOURCE] {len(master_only)} dòng chỉ có Trim Master, không có Tech Pack ref: {names}")
        else:
            report.append("✓ [SOURCE] Tất cả dòng đều có nguồn từ Tech Pack.")

        # 3. Conflict detection
        conflict_rows = [r for r in rows if any("CONFLICT" in a for a in (r.alerts or []))]
        if conflict_rows:
            report.append(
                f"⚠ [CONFLICT] {len(conflict_rows)} dòng có xung đột giữa Tech Pack và Trim Master. "
                f"Xem cột Alert trong Excel."
            )
        else:
            report.append("✓ [CONFLICT] Không có xung đột dữ liệu giữa Tech Pack và Trim Master.")

        # 4. Duplicate check
        true_dups = [a for a in alerts if hasattr(a, "code") and a.code == "duplicate"]
        if true_dups:
            report.append(f"⚠ [DUPLICATE] {len(true_dups)} cảnh báo trùng lặp thật.")
        else:
            report.append("✓ [DUPLICATE] Không có trùng lặp thật.")

        # 5. Colorway completeness
        multi_cw = [r for r in rows if r.colors and len(r.colors) > 1]
        if multi_cw:
            keys = sorted({k for r in multi_cw for k in r.colors})
            report.append(
                f"✓ [COLORWAY] {len(multi_cw)} dòng đa colorway: {', '.join(keys)}. "
                f"Đã tách cột màu trong Excel."
            )
        else:
            report.append("ℹ [COLORWAY] Không phát hiện đa colorway.")

        # 6. Email changes
        if email_changes:
            report.append(f"✓ [EMAIL] {len(email_changes)} thay đổi từ Email/Note đã áp dụng.")
        else:
            report.append("ℹ [EMAIL] Không có Email/Note override.")

        return report

    def _build_completion(self, rows: list) -> Dict:
        """Completion report (requirement 7): which fields were extracted vs which
        are still missing and need manual input. One place the user can read to
        know exactly what to fill, without re-scanning the whole file."""
        # Key fields the merchandiser needs on every trim row.
        key_fields = [
            ("material_code", "Mã vật liệu"),
            ("supplier",      "Nhà cung cấp"),
            ("spec",          "Spec"),
            ("placement",     "Vị trí"),
            ("consumption",   "Định mức"),
        ]
        total = len(rows)
        fields: Dict[str, Dict] = {}
        for fkey, flabel in key_fields:
            missing_items = [
                r.material_name for r in rows
                if not (getattr(r, fkey, None) and str(getattr(r, fkey)).strip())
            ]
            fields[fkey] = {
                "label":         flabel,
                "filled":        total - len(missing_items),
                "missing":       len(missing_items),
                "missing_items": missing_items[:50],
            }

        complete_items = sum(
            1 for r in rows
            if all(getattr(r, fk, None) and str(getattr(r, fk)).strip() for fk, _ in key_fields)
        )

        # pending_summary keeps the shape the frontend already reads.
        pending_summary = {
            "missing_code":      fields["material_code"]["missing"],
            "missing_supplier":  fields["supplier"]["missing"],
            "missing_spec":      fields["spec"]["missing"],
            "missing_placement": fields["placement"]["missing"],
        }

        return {
            "total_items":     total,
            "complete_items":  complete_items,
            "incomplete_items": total - complete_items,
            "fields":          fields,
            "pending_summary": pending_summary,
        }

    def _export(
        self,
        rows,
        alerts,
        meta: Dict,
        email_changes: List[str],
        self_check: List[str],
        master_path: Optional[str] = None,
        master_sheet: Optional[str] = None,
        techpack_path: Optional[str] = None,
    ):
        from backend.trimlist.excel_writer import TrimlistExcelWriter
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(OUTPUT_DIR, f"trimlist_v2_{ts}.xlsx")
        TrimlistExcelWriter().write(
            rows=rows,
            alerts=alerts,
            output_path=out_path,
            meta=meta,
            email_changes=email_changes,
            self_check=self_check,
            master_path=master_path,
            master_sheet=master_sheet,
            techpack_path=techpack_path,
        )
        return ts, out_path
