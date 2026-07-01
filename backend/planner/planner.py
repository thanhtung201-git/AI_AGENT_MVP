import json
import logging
from typing import Dict, Any, List
from backend.utils.groq_client import GroqClient

logger = logging.getLogger(__name__)

# ĐÃ SỬA: Nhân đôi các dấu ngoặc nhọn thành {{ và }} ở phần mẫu FORMAT OUTPUT JSON
PLANNER_SYSTEM_PROMPT = """Bạn là AI Planner cho hệ thống xử lý Purchase Order (PO) ngành may mặc.

Nhiệm vụ: Nhận yêu cầu từ người dùng và danh sách tools có sẵn, tạo ra một kế hoạch thực thi JSON.

# TOOLS CÓ SẴN
{tool_descriptions}

# QUY TẮC LÊN KẾ HOẠCH
1. Chỉ dùng các tool trong danh sách trên — không được tự bịa tool
2. Tool đọc file phải chạy trước — LUÔN dùng file_reader (hỗ trợ PDF, ảnh, Excel, Word, email)
3. Các extractor cần có text từ bước đọc file trước
4. validator phải chạy sau tất cả extractor
5. excel_exporter chỉ thêm nếu user yêu cầu xuất file
6. Không được dùng pdf_reader — tool đó đã bị xóa, thay bằng file_reader

# FORMAT OUTPUT (chỉ trả JSON, không thêm text)
{{
  "intent": "mô tả ngắn gọn mục tiêu",
  "steps": [
    {{
      "tool": "tên_tool",
      "args": {{"key": "value"}},
      "reason": "lý do chọn tool này"
    }}
  ],
  "notes": "ghi chú nếu có"
}}"""


class Planner:
    def __init__(self, llm_client: GroqClient = None):
        self.llm_client = llm_client or GroqClient()

    def _get_tool_descriptions(self, available_tools: Dict[str, Any]) -> str:
        if not available_tools:
            return "- file_reader: Đọc mọi loại file (PDF, ảnh, Excel, Word, email)\n- header_extractor: Trích xuất header PO\n- item_extractor: Trích xuất danh sách items\n- validator: Kiểm tra dữ liệu\n- excel_exporter: Xuất ra file Excel"
        lines = []
        for name, tool in available_tools.items():
            desc = getattr(tool, "description", "No description")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def generate_plan(
        self,
        user_request: str,
        available_tools: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Dùng LLM để phân tích yêu cầu và tạo plan động.
        context: thông tin từ memory về lần thử trước (nếu retry)
        """
        tool_descriptions = self._get_tool_descriptions(available_tools)
        system_prompt = PLANNER_SYSTEM_PROMPT.format(tool_descriptions=tool_descriptions)

        user_message = f"Yêu cầu: {user_request}"
        if context:
            user_message += f"\n\nContext từ lần thử trước:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
            user_message += "\n\nHãy điều chỉnh kế hoạch dựa trên thông tin trên."

        try:
            plan = self.llm_client.extract_json(system_prompt, user_message)
            logger.info(f"LLM generated plan: {plan.get('intent')}")

            # Validate plan có đủ field cần thiết
            if "steps" not in plan or not isinstance(plan["steps"], list):
                raise ValueError("Plan thiếu field 'steps'")

            return plan

        except Exception as e:
            logger.error(f"LLM planning failed: {e}. Fallback sang heuristic.")
            return self._fallback_plan(user_request)

    def _fallback_plan(self, user_request: str) -> Dict[str, Any]:
        """Fallback heuristic nếu LLM lỗi."""
        steps = []
        req = user_request.lower()

        steps.append({"tool": "file_reader", "args": {}, "reason": "Đọc file tự động"})

        steps += [
            {"tool": "header_extractor", "args": {}, "reason": "Trích xuất header"},
            {"tool": "item_extractor", "args": {}, "reason": "Trích xuất items"},
            {"tool": "validator", "args": {}, "reason": "Kiểm tra dữ liệu"},
        ]

        if "export" in req or "excel" in req:
            steps.append({"tool": "excel_exporter", "args": {}, "reason": "Xuất Excel"})

        return {"intent": "extract_po (fallback)", "steps": steps, "notes": "Fallback plan do LLM lỗi"}