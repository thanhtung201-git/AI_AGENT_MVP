from typing import Dict, Any, List, Optional


class ShortTermMemory:
    """
    In-memory storage cho trạng thái thực thi hiện tại.
    History được dùng để cung cấp context cho Reviewer và Planner khi retry.
    """

    def __init__(self):
        self.state: Dict[str, Any] = {}
        self.history: List[Dict[str, Any]] = []

    # ── State ──────────────────────────────────────────────────────────────

    def set(self, key: str, value: Any):
        self.state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    # ── History ────────────────────────────────────────────────────────────

    def add_to_history(self, event: Dict[str, Any]):
        self.history.append(event)

    def get_history(self) -> List[Dict[str, Any]]:
        return self.history

    def get_recent_history(self, n: int = 5) -> List[Dict[str, Any]]:
        """Trả về n sự kiện gần nhất — dùng để inject context vào LLM."""
        return self.history[-n:]

    # ── Retry context ──────────────────────────────────────────────────────

    def get_retry_context(self) -> Dict[str, Any]:
        """
        Tóm tắt lịch sử thực thi để gửi cho Planner khi retry.
        Bao gồm: số lần thử, tools đã dùng, lỗi gặp phải.
        """
        attempts = [h for h in self.history if h.get("action") == "plan"]
        reflections = [h for h in self.history if h.get("action") == "reflect"]
        tool_errors = [
            {"tool": h["tool"], "error": h.get("error")}
            for h in self.history
            if h.get("action") == "execute_tool" and not h.get("success")
        ]

        return {
            "total_attempts": len(attempts),
            "tools_tried": [
                step
                for h in attempts
                for step in h.get("steps", [])
            ],
            "tool_errors": tool_errors,
            "last_review": reflections[-1] if reflections else None,
            "user_request": self.state.get("user_request"),
        }

    def get_failed_tools(self) -> List[str]:
        """Danh sách tools đã fail — Planner dùng để tránh hoặc thay thế."""
        return [
            h["tool"]
            for h in self.history
            if h.get("action") == "execute_tool" and not h.get("success")
        ]

    def get_last_review(self) -> Optional[Dict[str, Any]]:
        """Lấy kết quả review gần nhất."""
        reflections = [h for h in self.history if h.get("action") == "reflect"]
        return reflections[-1] if reflections else None

    # ── Utils ──────────────────────────────────────────────────────────────

    def clear(self):
        self.state.clear()
        self.history.clear()

    def summary(self) -> Dict[str, Any]:
        """Tóm tắt trạng thái hiện tại — dùng để log hoặc debug."""
        return {
            "state_keys": list(self.state.keys()),
            "history_count": len(self.history),
            "last_action": self.history[-1].get("action") if self.history else None,
        }