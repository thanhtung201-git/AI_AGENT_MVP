import logging
import json
from typing import Dict, Any, List, Optional
from supabase import create_client, Client
from backend.config.settings import settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Handles connection and queries to Supabase."""

    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_KEY
        self.mock_mode = False

        if self.url and self.key:
            try:
                self.client: Client = create_client(self.url, self.key)
                logger.info("Connected to Supabase.")
            except Exception as e:
                logger.error(f"Failed to connect to Supabase: {e}")
                self.mock_mode = True
        else:
            logger.warning("Supabase credentials not found. Running in mock mode.")
            self.mock_mode = True

    # ── purchase_orders ───────────────────────────────────────────────────────

    def insert_po(self, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[int]:
        """
        Insert PO header vào purchase_orders, sau đó insert từng item vào po_items.
        Trả về po_id nếu thành công, None nếu thất bại.
        """
        if self.mock_mode:
            logger.info(f"[Mock] insert_po: {header.get('po_number')} | {len(items)} items")
            return None

        try:
            # 1. Insert header
            po_row = {
                "po_number":      header.get("po_number"),
                "buyer":          header.get("buyer"),
                "seller":         header.get("seller"),
                "order_date":     header.get("order_date"),
                "delivery_date":  header.get("delivery_date"),
                "ship_date":      header.get("ship_date"),
                "payment_terms":  header.get("payment_terms"),
                "incoterm":       header.get("incoterm"),
                "currency":       header.get("currency") or "USD",
                "season":         header.get("season"),
                "notes":          header.get("notes"),
                "total_quantity": sum(i.get("total_quantity") or 0 for i in items),
                "total_amount":   sum(i.get("total_price") or 0.0 for i in items),
            }
            resp = self.client.table("purchase_orders").insert(po_row).execute()
            if not (resp.data and len(resp.data) > 0):
                logger.error("Insert purchase_orders failed: no data returned")
                return None

            po_id = resp.data[0]["id"]
            logger.info(f"Inserted purchase_orders id={po_id} | PO={header.get('po_number')}")

            # 2. Insert items
            if items:
                item_rows = []
                for it in items:
                    size_val = it.get("size_breakdown")
                    item_rows.append({
                        "po_id":          po_id,
                        "po_number":      header.get("po_number"),
                        "style_code":     it.get("style_code"),
                        "style_name":     it.get("style_name"),
                        "color_name":     it.get("color_name"),
                        "size_breakdown": json.dumps(size_val) if size_val else None,
                        "total_quantity": it.get("total_quantity") or 0,
                        "unit_price":     it.get("unit_price") or 0,
                        "total_price":    it.get("total_price") or 0,
                    })
                resp2 = self.client.table("po_items").insert(item_rows).execute()
                logger.info(f"Inserted {len(resp2.data)} items vào po_items")

            return po_id

        except Exception as e:
            logger.error(f"insert_po error: {e}")
            return None

    def get_po(self, po_number: str) -> Dict[str, Any]:
        if self.mock_mode:
            return {}
        try:
            resp = self.client.table("purchase_orders").select("*").eq("po_number", po_number).execute()
            return resp.data[0] if resp.data else {}
        except Exception as e:
            logger.error(f"get_po error: {e}")
            return {}

    def get_po_list(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return []
        try:
            resp = (
                self.client.table("purchase_orders")
                .select("id, po_number, buyer, seller, order_date, delivery_date, total_quantity, total_amount, created_at")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"get_po_list error: {e}")
            return []

    # ── execution_logs ────────────────────────────────────────────────────────

    def insert_execution_log(self, log_data: Dict[str, Any]) -> bool:
        if self.mock_mode:
            logger.info(f"[Mock] execution_log: {log_data}")
            return True
        try:
            resp = self.client.table("execution_logs").insert(log_data).execute()
            return bool(resp.data)
        except Exception as e:
            logger.error(f"insert_execution_log error: {e}")
            return False
