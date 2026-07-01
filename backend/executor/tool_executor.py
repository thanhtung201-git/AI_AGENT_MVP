import importlib
import inspect
import logging
from typing import Dict, Any, List, Optional
from backend.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Declares which prior tool outputs feed into each tool's inputs.
# Key: tool_name  →  Value: {tool_input_arg: (source_tool, source_key)}
TOOL_INPUT_MAP: Dict[str, Dict[str, tuple]] = {
    "header_extractor": {
        "text": ("file_reader", "text"),
    },
    "item_extractor": {
        "text": ("file_reader", "text"),
    },
    "validator": {
        "header": ("header_extractor", "header"),
        "items":  ("item_extractor",  "items"),
    },
    "excel_exporter": {
        "header": ("header_extractor", "header"),
        "items":  ("item_extractor",  "items"),
    },
}


class ToolExecutor:
    def __init__(self):
        self.tool_registry: Dict[str, BaseTool] = {}
        self._discover_tools()

    # ------------------------------------------------------------------ #
    #  Tool discovery                                                      #
    # ------------------------------------------------------------------ #

    def _discover_tools(self):
        """Auto-load all tools from backend.tools.*"""
        tool_modules = [
            "file_reader",
            "header_extractor",
            "item_extractor",
            "validator",
            "excel_exporter",
        ]
        for module_name in tool_modules:
            try:
                module = importlib.import_module(f"backend.tools.{module_name}")
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseTool)
                        and obj is not BaseTool
                    ):
                        instance = obj()
                        self.tool_registry[instance.name] = instance
                        logger.info(
                            f"Registered tool: {instance.name} — {instance.description}"
                        )
            except ImportError as e:
                logger.warning(f"Cannot load tool module '{module_name}': {e}")
            except Exception as e:
                logger.error(f"Error registering tool '{module_name}': {e}")

    # ------------------------------------------------------------------ #
    #  Schema helpers for Planner                                          #
    # ------------------------------------------------------------------ #

    def get_tool_descriptions(self) -> Dict[str, str]:
        return {
            name: getattr(tool, "description", "No description")
            for name, tool in self.tool_registry.items()
        }

    def get_tool_schemas(self) -> Dict[str, Any]:
        schemas = {}
        for name, tool in self.tool_registry.items():
            schemas[name] = {
                "description":   getattr(tool, "description", ""),
                "input_schema":  getattr(tool, "input_schema",  {}),
                "output_schema": getattr(tool, "output_schema", {}),
            }
        return schemas

    # ------------------------------------------------------------------ #
    #  Single-tool execution (low-level)                                   #
    # ------------------------------------------------------------------ #

    def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute one tool by name with explicit kwargs."""
        if tool_name not in self.tool_registry:
            logger.error(
                f"Tool '{tool_name}' not found. Available: {list(self.tool_registry.keys())}"
            )
            return {"error": f"Tool '{tool_name}' not found", "success": False}

        tool = self.tool_registry[tool_name]
        logger.info(f"Executing: {tool_name} | args: {list(kwargs.keys())}")
        try:
            result = tool.execute(**kwargs)
            if "success" not in result:
                result["success"] = True
            return result
        except Exception as e:
            logger.error(f"Tool '{tool_name}' crashed: {e}")
            return {"error": str(e), "success": False}

    # ------------------------------------------------------------------ #
    #  Pipeline execution (high-level) — with context chaining            #
    # ------------------------------------------------------------------ #

    def execute_pipeline(
        self,
        steps: List[str],
        initial_kwargs: Optional[Dict[str, Any]] = None,
        stop_on_failure: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a list of tools in sequence, automatically wiring outputs of
        earlier tools as inputs to later tools via TOOL_INPUT_MAP.

        Args:
            steps:            Ordered list of tool names to execute.
            initial_kwargs:   Seed values available to all tools (e.g. file_path).
            stop_on_failure:  If True, abort remaining steps when a tool fails.

        Returns:
            {
                "results":          {tool_name: result_dict, ...},
                "success":          bool,          # True if all tools succeeded
                "failed_tools":     [tool_name],
                "confidence_score": float,         # fraction of tools that succeeded
            }
        """
        context: Dict[str, Any] = {}          # tool_name → result dict
        seed: Dict[str, Any] = initial_kwargs or {}
        results: Dict[str, Any] = {}
        failed: List[str] = []

        for tool_name in steps:
            kwargs = self._build_kwargs(tool_name, context, seed)
            missing = self._check_missing_required(tool_name, kwargs)

            if missing:
                error_msg = f"Missing required inputs: {missing}"
                logger.warning(f"Skipping {tool_name} — {error_msg}")
                result = {"error": error_msg, "success": False}
            else:
                result = self.execute_tool(tool_name, **kwargs)

            results[tool_name] = result
            context[tool_name] = result

            if not result.get("success", False):
                failed.append(tool_name)
                logger.warning(f"Tool {tool_name} failed: {result.get('error')}")
                if stop_on_failure:
                    logger.info(f"Stopping pipeline after failed tool: {tool_name}")
                    break

        total   = len(steps)
        passed  = total - len(failed)
        # Count only tools that were actually run
        run     = len(results)
        score   = passed / run if run > 0 else 0.0

        return {
            "results":          results,
            "success":          len(failed) == 0,
            "failed_tools":     failed,
            "confidence_score": score,
        }

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _build_kwargs(
        self,
        tool_name: str,
        context: Dict[str, Any],
        seed: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build kwargs for a tool by:
          1. Starting with seed values (e.g. file_path from the user request).
          2. Overlaying values resolved from TOOL_INPUT_MAP using prior results.
        """
        kwargs: Dict[str, Any] = dict(seed)  # shallow copy so we don't mutate seed

        input_map = TOOL_INPUT_MAP.get(tool_name, {})
        for arg_name, (source_tool, source_key) in input_map.items():
            if source_tool in context:
                source_result = context[source_tool]
                if source_result.get("success") and source_key in source_result:
                    kwargs[arg_name] = source_result[source_key]
                    logger.debug(
                        f"  {tool_name}.{arg_name} ← {source_tool}.{source_key}"
                    )
                else:
                    logger.debug(
                        f"  {tool_name}.{arg_name}: source '{source_tool}.{source_key}' "
                        f"unavailable (tool failed or key missing)"
                    )

        return kwargs

    def _check_missing_required(
        self, tool_name: str, kwargs: Dict[str, Any]
    ) -> List[str]:
        """
        Return a list of required input keys that are absent from kwargs.
        Uses the tool's input_schema if available, otherwise falls back to
        TOOL_INPUT_MAP keys.
        """
        tool = self.tool_registry.get(tool_name)
        if tool is None:
            return []

        # Prefer the tool's own declared required fields
        schema = getattr(tool, "input_schema", {})
        required_fields: List[str] = schema.get("required", [])

        # Fallback: treat all TOOL_INPUT_MAP entries as required
        if not required_fields:
            required_fields = list(TOOL_INPUT_MAP.get(tool_name, {}).keys())

        return [f for f in required_fields if f not in kwargs]