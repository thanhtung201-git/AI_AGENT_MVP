import logging
from typing import Dict, Any, List, Optional
from backend.database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    Lưu trữ bền vững cho agent.
    - PO data đã extract thành công
    - Execution log để phân tích pattern
    - Customer template patterns (buyer X thường dùng format nào)
    """

    def __init__(self, db_client: SupabaseClient = None):
        self.db = db_client or SupabaseClient()

    # ── Lưu kết quả ────────────────────────────────────────────────────────

    def save_po_data(self, po_data: Dict[str, Any]) -> bool:
        """Lưu PO đã extract thành công vào database."""
        try:
            return self.db.insert_po(po_data)
        except Exception as e:
            logger.error(f"Lỗi lưu PO data: {e}")
            return False

    def save_execution_log(self, log_data: Dict[str, Any]) -> bool:
        """
        Lưu log thực thi.
        Dùng để phân tích: buyer nào hay lỗi gì, tool nào hiệu quả nhất.
        """
        try:
            return self.db.insert_execution_log(log_data)
        except Exception as e:
            logger.error(f"Lỗi lưu execution log: {e}")
            return False

    def save_buyer_pattern(
        self,
        buyer_name: str,
        successful_plan: List[str],
        file_format: str,
        notes: str = "",
    ) -> bool:
        """
        Lưu pattern thành công theo buyer.
        Lần sau gặp PO từ cùng buyer → Planner có thể dùng pattern này ngay.
        """
        try:
            pattern = {
                "buyer_name": buyer_name,
                "successful_plan": successful_plan,
                "file_format": file_format,
                "notes": notes,
            }
            return self.db.upsert_buyer_pattern(pattern)
        except Exception as e:
            logger.error(f"Lỗi lưu buyer pattern: {e}")
            return False

    # ── Truy xuất ──────────────────────────────────────────────────────────

    def retrieve_po(self, po_number: str) -> Dict[str, Any]:
        """Lấy PO đã lưu theo số PO."""
        try:
            return self.db.get_po(po_number)
        except Exception as e:
            logger.error(f"Lỗi lấy PO {po_number}: {e}")
            return {}

    def get_buyer_pattern(self, buyer_name: str) -> Optional[Dict[str, Any]]:
        """
        Lấy plan pattern đã thành công cho buyer này.
        Planner dùng để ưu tiên strategy đã proven.
        """
        try:
            return self.db.get_buyer_pattern(buyer_name)
        except Exception as e:
            logger.error(f"Lỗi lấy buyer pattern cho {buyer_name}: {e}")
            return None

    def get_recent_failed_patterns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Lấy các pattern thất bại gần đây.
        Dùng để phân tích và cải thiện prompts/tools.
        """
        try:
            return self.db.get_failed_executions(limit=limit)
        except Exception as e:
            logger.error(f"Lỗi lấy failed patterns: {e}")
            return []