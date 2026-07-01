import logging
from typing import Dict, Any
from backend.planner.planner import Planner
from backend.executor.tool_executor import ToolExecutor
from backend.reflection.reviewer import Reviewer
from backend.memory.short_term_memory import ShortTermMemory
from backend.memory.long_term_memory import LongTermMemory

logger = logging.getLogger(__name__)

print(">>> LOADED po_agent.py version: WITH _merge_po_data")
class POAgent:
    def __init__(self):
        self.executor = ToolExecutor()
        self.planner = Planner()
        self.reviewer = Reviewer()
        self.memory = ShortTermMemory()
        self.long_term_memory = LongTermMemory()

    def process_request(self, user_request: str, file_path: str = None) -> Dict[str, Any]:
        """
        Main agent loop: Plan → Act → Reflect → (Retry với chiến lược mới nếu cần)
        """
        logger.info(f"Agent bắt đầu xử lý: {user_request}")
        self.memory.clear()
        self.memory.set("user_request", user_request)
        self.memory.set("file_path", file_path)

        max_retries = self.reviewer.config.get("max_retries", 3)
        success = False
        final_result = {}
        review_detail = {}
        retry_context = None

        for attempt in range(max_retries + 1):
            logger.info(f"--- Lần thử {attempt + 1}/{max_retries + 1} ---")

            # ── 1. PLAN ───────────────────────────────────────────────────────
            plan = self.planner.generate_plan(
                user_request=user_request,
                available_tools=self.executor.tool_registry,
                context=retry_context,
            )
            self.memory.set("current_plan", plan)
            self.memory.add_to_history({
                "action": "plan",
                "attempt": attempt + 1,
                "intent": plan.get("intent"),
                "steps": [s["tool"] for s in plan.get("steps", [])],
            })
            logger.info(
                f"Plan: {plan.get('intent')} | "
                f"Steps: {[s['tool'] for s in plan.get('steps', [])]}"
            )

            # ── 2. ACT ────────────────────────────────────────────────────────
            execution_results: Dict[str, Any] = {}

            # Seed context with user-supplied values available to all tools.
            # Keys match exactly what each tool's execute() expects as kwargs.
            context_data: Dict[str, Any] = {}
            if file_path:
                context_data["file_path"] = file_path

            for step in plan.get("steps", []):
                tool_name = step["tool"]
                # Start from planner-supplied static args, then overlay context.
                args = {**step.get("args", {}), **_build_args(tool_name, context_data)}

                result = self.executor.execute_tool(tool_name, **args)
                execution_results[tool_name] = result

                if result.get("success"):
                    # Propagate outputs into context for downstream tools.
                    # Use the exact kwarg names each tool declares.
                    _update_context(tool_name, result, context_data)
                else:
                    logger.warning(f"Tool {tool_name} thất bại: {result.get('error')}")

                self.memory.add_to_history({
                    "action": "execute_tool",
                    "attempt": attempt + 1,
                    "tool": tool_name,
                    "success": result.get("success", False),
                    "error": result.get("error"),
                })

            # ── 3. REFLECT ────────────────────────────────────────────────────
            # Wrap execution_results under "results" so reviewer._check_required_tools
            # can find tool outcomes via extraction_results.get("results", {}).
            extraction_summary = {
                "results": execution_results,          # ← the key the reviewer expects
                "data": context_data,
            }

            validation_results = execution_results.get("validator", {})

            is_acceptable, feedback, review_detail = self.reviewer.evaluate(
                extraction_results=extraction_summary,
                validation_results=validation_results,
                execution_history=self.memory.get_history(),
            )

            self.memory.add_to_history({
                "action": "reflect",
                "attempt": attempt + 1,
                "verdict": review_detail.get("verdict"),
                "confidence_score": review_detail.get("confidence_score"),
                "feedback": feedback,
            })

            if is_acceptable:
                success = True
                final_result = execution_results
                logger.info(f"Thành công ở lần thử {attempt + 1}!")
                break
            else:
                logger.warning(f"Review FAIL lần {attempt + 1}: {feedback}")
                if attempt < max_retries:
                    retry_context = {
                        "previous_attempt": attempt + 1,
                        "previous_plan": [s["tool"] for s in plan.get("steps", [])],
                        "review_feedback": feedback,
                        "missing_fields": review_detail.get("missing_fields", []),
                        "errors": review_detail.get("errors", []),
                        "retry_strategy": review_detail.get("retry_strategy", ""),
                        "suggested_tool_adjustment": review_detail.get(
                            "suggested_tool_adjustment", ""
                        ),
                    }
                    logger.info(
                        f"Retry context cho lần {attempt + 2}: "
                        f"{retry_context.get('retry_strategy')}"
                    )

        # ── 4. FINISH ─────────────────────────────────────────────────────────
        if success:
            self.long_term_memory.save_execution_log({
                "user_request": user_request,
                "file_path": file_path,
                "attempts": len(
                    [h for h in self.memory.get_history() if h["action"] == "plan"]
                ),
                "status": "success",
                "final_confidence": review_detail.get("confidence_score"),
            })
            return {
                "status": "success",
                "results": final_result,
                "confidence_score": review_detail.get("confidence_score"),
                "history": self.memory.get_history(),
            }
        else:
            logger.error(f"Agent thất bại sau {max_retries + 1} lần thử.")
            return {
                "status": "failed",
                "reason": review_detail.get("errors", ["Unknown error"]),
                "last_feedback": review_detail.get("summary", ""),
                "history": self.memory.get_history(),
            }


# ── Context helpers (module-level, keeps POAgent clean) ──────────────────────

# Maps tool_name → {kwarg_name: context_key}
# "what kwarg does this tool need, and where in context_data does it live?"
_TOOL_ARG_SOURCES: Dict[str, Dict[str, str]] = {
    "file_reader":      {"file_path": "file_path"},
    "header_extractor": {"text": "text"},
    "item_extractor":   {"text": "text"},
    "validator": {
        "header": "header",
        "items":  "items",
    },
    "excel_exporter": {
        "header": "header",
        "items":  "items",
    },
}

_TOOL_OUTPUT_MAP: Dict[str, Dict[str, str]] = {
    "file_reader":      {"text": "text"},
    "header_extractor": {"header": "header"},
    "item_extractor":   {"items": "items"},
    "validator":        {"validation_report": "validation_report"},
    "excel_exporter":   {"output_path": "excel_path"},
}


def _build_args(tool_name: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve the kwargs a tool needs from the current context."""
    args: Dict[str, Any] = {}
    for kwarg, ctx_key in _TOOL_ARG_SOURCES.get(tool_name, {}).items():
        if ctx_key in context_data:
            args[kwarg] = context_data[ctx_key]
    return args


def _update_context(
    tool_name: str, result: Dict[str, Any], context_data: Dict[str, Any]
) -> None:
    """Store a successful tool's outputs into context for downstream tools."""
    for result_key, ctx_key in _TOOL_OUTPUT_MAP.get(tool_name, {}).items():
        if result_key in result:
            context_data[ctx_key] = result[result_key]
            logger.debug(f"  context['{ctx_key}'] ← {tool_name}.{result_key}")