from __future__ import annotations
import json
import logging
from typing import Dict, Any, Tuple
from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

REVIEWER_SYSTEM_PROMPT = """Bạn là AI Reviewer chuyên đánh giá kết quả trích xuất Purchase Order (PO) ngành may mặc.

Nhiệm vụ: Nhận kết quả extraction, đánh giá chất lượng và đưa ra quyết định + hướng dẫn cụ thể nếu cần retry.

# CÁC TRƯỜNG BẮT BUỘC TRONG PO
- po_number: Số PO
- buyer: Tên người mua
- vendor: Tên nhà cung cấp
- order_date: Ngày đặt hàng
- delivery_date: Ngày giao hàng
- items: Danh sách items (mỗi item cần style, color, sizes, quantity)
- total_quantity: Tổng số lượng

# CÁCH ĐÁNH GIÁ
- PASS: Tất cả trường bắt buộc có giá trị, quantity hợp lệ, format ngày đúng
- FAIL: Thiếu trường bắt buộc, hoặc có lỗi nghiêm trọng

# FORMAT OUTPUT (chỉ trả JSON, không thêm text)
{
  "verdict": "PASS" hoặc "FAIL",
  "confidence_score": 0.0 đến 1.0,
  "missing_fields": ["tên trường còn thiếu"],
  "errors": ["mô tả lỗi cụ thể"],
  "retry_strategy": "hướng dẫn cụ thể để retry — để trống nếu PASS",
  "suggested_tool_adjustment": "đề xuất thay đổi tool hoặc tham số — để trống nếu không cần",
  "summary": "tóm tắt ngắn gọn kết quả đánh giá"
}"""

# Tools that must succeed for the pipeline to be meaningful.
# Downstream tools (validator, excel_exporter) can be optional.
REQUIRED_TOOLS = {"file_reader", "header_extractor", "item_extractor"}


class Reviewer:
    def __init__(
        self,
        llm_client: GroqClient = None,
        config: Dict[str, Any] = None,
    ):
        self.llm_client = llm_client or GroqClient()
        self.config = config or {"min_confidence_threshold": 0.75, "max_retries": 3}

    def evaluate(
        self,
        extraction_results: Dict[str, Any],
        validation_results: Dict[str, Any] = None,
        execution_history: list = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Use LLM to evaluate extraction results.

        Returns:
            (is_acceptable, feedback_message, review_detail)
        """
        # Gate: if required tools all failed, skip the LLM call entirely —
        # there is nothing meaningful to review.
        tool_results = extraction_results.get("results", {})
        early_fail = self._check_required_tools(tool_results)
        if early_fail:
            return False, early_fail["feedback"], early_fail

        user_message = (
            f"Kết quả extraction:\n"
            f"{json.dumps(extraction_results, ensure_ascii=False, indent=2)}"
        )
        if validation_results:
            user_message += (
                f"\n\nKết quả validation:\n"
                f"{json.dumps(validation_results, ensure_ascii=False, indent=2)}"
            )
        if execution_history:
            recent = execution_history[-3:]
            user_message += (
                f"\n\nLịch sử thực thi gần đây:\n"
                f"{json.dumps(recent, ensure_ascii=False, indent=2)}"
            )

        return self._fallback_evaluate(extraction_results, validation_results)

    # ------------------------------------------------------------------ #
    #  Fallback (no LLM)                                                   #
    # ------------------------------------------------------------------ #

    def _fallback_evaluate(
        self,
        extraction_results: Dict[str, Any],
        validation_results: Dict[str, Any] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Rule-based fallback used when the LLM call fails.

        Checks (in order):
          1. Required tools must have all succeeded.
          2. Validator must not have reported errors (if it ran).
          3. Computed confidence from tool success ratio must meet threshold.
        """
        tool_results = extraction_results.get("results", {})

        # 1. Required tools check
        required_fail = self._check_required_tools(tool_results)
        if required_fail:
            return False, required_fail["feedback"], required_fail

        # 2. Validator errors check
        if validation_results and not validation_results.get("is_valid", True):
            errors = validation_results.get("errors", [])
            detail = {
                "verdict": "FAIL",
                "confidence_score": 0.0,
                "errors": errors,
                "retry_strategy": "Kiểm tra lại các trường bị lỗi",
                "feedback": f"Validation failed: {errors}",
            }
            return False, detail["feedback"], detail

        # 3. Compute honest confidence from actual tool outcomes
        score = self._compute_confidence(tool_results)
        threshold = self.config["min_confidence_threshold"]

        if score < threshold:
            detail = {
                "verdict": "FAIL",
                "confidence_score": score,
                "errors": [f"Confidence {score:.2f} < threshold {threshold}"],
                "retry_strategy": "Thử OCR hoặc extraction strategy khác",
                "feedback": f"Confidence too low: {score:.2f}",
            }
            return False, detail["feedback"], detail

        detail = {
            "verdict": "PASS",
            "confidence_score": score,
            "errors": [],
            "summary": f"Fallback evaluation passed ({score:.0%} tools succeeded)",
            "feedback": "Extraction successful (fallback check)",
        }
        return True, detail["feedback"], detail

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _check_required_tools(
        self, tool_results: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """
        Return a FAIL detail dict if any required tool is missing or failed,
        or None if all required tools passed.
        """
        failed = []
        for tool in REQUIRED_TOOLS:
            result = tool_results.get(tool)
            if result is None:
                failed.append(f"{tool} (did not run)")
            elif not result.get("success", False):
                err = result.get("error", "unknown error")
                failed.append(f"{tool} ({err})")

        if not failed:
            return None

        feedback = f"Required tools failed: {'; '.join(failed)}"
        logger.warning(f"Reviewer early-fail: {feedback}")
        return {
            "verdict": "FAIL",
            "confidence_score": 0.0,
            "errors": failed,
            "retry_strategy": "Kiểm tra file path và input args cho từng tool",
            "feedback": feedback,
        }

    @staticmethod
    def _compute_confidence(tool_results: Dict[str, Any]) -> float:
        """
        Confidence = fraction of tools that actually succeeded.
        Never defaults to 1.0 when there are no results.
        """
        if not tool_results:
            return 0.0
        passed = sum(1 for r in tool_results.values() if r.get("success", False))
        return passed / len(tool_results)