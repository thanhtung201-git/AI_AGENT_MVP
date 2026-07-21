import logging
import json
import re
from datetime import datetime
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

    @staticmethod
    def _parse_date(value: Any) -> Optional[str]:
        """Convert various date formats to ISO yyyy-mm-dd for Supabase."""
        if not value:
            return None
        s = str(value).strip()
        # Remove ordinal suffixes: 22ND → 22, 1ST → 1, 3RD → 3
        s = re.sub(r"(\d+)(ST|ND|RD|TH)", lambda m: m.group(1), s, flags=re.IGNORECASE)
        # Normalize separators
        s = s.strip().rstrip(",").strip()
        for fmt in (
            "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y-%m-%d",
            "%d %b %Y", "%d %B %Y", "%B %d %Y", "%b %d %Y",
            "%d %b, %Y", "%d %B, %Y",
        ):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        # Extract yyyy-mm-dd substring
        m = re.search(r"\d{4}-\d{2}-\d{2}", s)
        if m:
            return m.group(0)
        logger.warning(f"Cannot parse date: {value!r}")
        return None

    # ── purchase_orders + po_items ────────────────────────────────────────────

    def insert_po(self, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Optional[int]:
        if self.mock_mode:
            logger.info(f"[Mock] insert_po: {header.get('po_number')} | {len(items)} items")
            return None
        try:
            po_row = {
                "po_number":      header.get("po_number"),
                "buyer":          header.get("buyer"),
                "seller":         header.get("seller"),
                "order_date":     self._parse_date(header.get("order_date")),
                "delivery_date":  self._parse_date(header.get("delivery_date")),
                "ship_date":      self._parse_date(header.get("ship_date")),
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
                        "size":           it.get("size"),
                        "size_breakdown": json.dumps(size_val) if size_val else None,
                        "total_quantity": it.get("total_quantity") or 0,
                        "unit_price":     it.get("unit_price") or 0,
                        "total_price":    it.get("total_price") or 0,
                    })
                self.client.table("po_items").insert(item_rows).execute()
                logger.info(f"Inserted {len(item_rows)} items vào po_items (po_id={po_id})")

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

    # ── trimlist_sessions + trim_items ────────────────────────────────────────

    def insert_trimlist_session(
        self,
        po_id: Optional[int],
        meta: Dict[str, Any],
        trim_items: List[Dict[str, Any]],
        excel_path: str = "",
    ) -> Optional[int]:
        if self.mock_mode:
            logger.info(f"[Mock] insert_trimlist_session: {meta.get('po_number')}")
            return None
        try:
            session_row = {
                "po_id":         po_id,
                "po_number":     meta.get("po_number"),
                "style_code":    meta.get("style_code"),
                "style_name":    meta.get("style_name"),
                "buyer":         meta.get("buyer"),
                "factory":       meta.get("factory"),
                "order_qty":     int(str(meta.get("order_qty", "0")).replace(",", "").replace(" pcs", "")) if meta.get("order_qty") else 0,
                "techpack_file": meta.get("techpack_file", ""),
                "item_count":    len(trim_items),
                "excel_path":    excel_path,
            }
            resp = self.client.table("trimlist_sessions").insert(session_row).execute()
            if not (resp.data and len(resp.data) > 0):
                return None

            session_id = resp.data[0]["id"]

            if trim_items:
                rows = [
                    {
                        "session_id":      session_id,
                        "po_number":       meta.get("po_number"),
                        "supplier_code":   it.get("supplier_code"),
                        "trim_item":       it.get("trim_item", ""),
                        "spec":            it.get("spec"),
                        "supplier":        it.get("supplier"),
                        "qty_per_garment": it.get("qty_per_garment"),
                        "unit":            it.get("unit"),
                        "total_qty":       it.get("total_qty"),
                        "placement":       it.get("placement"),
                        "source_file":     it.get("_source_file"),
                    }
                    for it in trim_items
                ]
                self.client.table("trim_items").insert(rows).execute()
                logger.info(f"Inserted {len(rows)} trim_items (session_id={session_id})")

            return session_id
        except Exception as e:
            logger.error(f"insert_trimlist_session error: {e}")
            return None

    def get_trimlist_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return []
        try:
            resp = (
                self.client.table("trimlist_sessions")
                .select("id, po_number, style_code, item_count, order_qty, techpack_file, created_at")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"get_trimlist_sessions error: {e}")
            return []

    def get_trim_items_by_sessions(self, session_ids: List[int]) -> List[Dict[str, Any]]:
        """Lấy tất cả trim_items thuộc danh sách session_id."""
        if self.mock_mode or not session_ids:
            return []
        try:
            resp = (
                self.client.table("trim_items")
                .select("session_id, po_number, supplier_code, trim_item, spec, supplier, qty_per_garment, unit, total_qty, placement")
                .in_("session_id", session_ids)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"get_trim_items_by_sessions error: {e}")
            return []

    # ── recap_sessions + recap_items ──────────────────────────────────────────

    def insert_recap_session(
        self,
        po_number: str,
        order_filename: str,
        trimlist_ref: str,
        items: List[Dict[str, Any]],
        stats: Dict[str, int],
        excel_path: str = "",
    ) -> Optional[int]:
        if self.mock_mode:
            logger.info(f"[Mock] insert_recap_session: {po_number}")
            return None
        try:
            verdict = "DAT" if stats.get("error_count", 0) == 0 else "KHONG_DAT"
            session_row = {
                "po_number":      po_number,
                "order_filename": order_filename,
                "trimlist_ref":   trimlist_ref,
                "total_items":    stats.get("total", 0),
                "ok_count":       stats.get("ok_count", 0),
                "warning_count":  stats.get("warning_count", 0),
                "error_count":    stats.get("error_count", 0),
                "verdict":        verdict,
                "excel_path":     excel_path,
            }
            resp = self.client.table("recap_sessions").insert(session_row).execute()
            if not (resp.data and len(resp.data) > 0):
                return None

            session_id = resp.data[0]["id"]

            if items:
                rows = [
                    {
                        "session_id":     session_id,
                        "item_no":        it.get("no"),
                        "supplier_code":  it.get("supplier_code"),
                        "trim_item":      it.get("trim_item"),
                        "spec_order":     it.get("spec"),
                        "spec_ref":       it.get("spec_ref"),
                        "supplier_order": it.get("supplier"),
                        "supplier_ref":   it.get("supplier_ref"),
                        "qty_ordered":    it.get("qty_ordered"),
                        "qty_required":   it.get("qty_required"),
                        "unit_order":     it.get("unit"),
                        "unit_ref":       it.get("unit_ref"),
                        "status":         it.get("status"),
                        "error_detail":   it.get("error_detail"),
                    }
                    for it in items
                ]
                self.client.table("recap_items").insert(rows).execute()
                logger.info(f"Inserted {len(rows)} recap_items (session_id={session_id})")

            return session_id
        except Exception as e:
            logger.error(f"insert_recap_session error: {e}")
            return None

    def get_recap_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return []
        try:
            resp = (
                self.client.table("recap_sessions")
                .select("id, po_number, order_filename, total_items, ok_count, warning_count, error_count, verdict, created_at")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"get_recap_sessions error: {e}")
            return []

    # ── scan_log ──────────────────────────────────────────────────────────────

    def scan_log_get_all(self) -> Dict[str, Any]:
        """Trả về dict {filename: entry} giống format JSON log cũ."""
        if self.mock_mode:
            return {}
        try:
            resp = self.client.table("scan_log").select("*").order("processed_at", desc=True).execute()
            return {row["filename"]: row for row in (resp.data or [])}
        except Exception as e:
            logger.error(f"scan_log_get_all error: {e}")
            return {}

    def scan_log_get_filenames(self) -> List[str]:
        if self.mock_mode:
            return []
        try:
            resp = self.client.table("scan_log").select("filename").execute()
            return [r["filename"] for r in (resp.data or [])]
        except Exception as e:
            logger.error(f"scan_log_get_filenames error: {e}")
            return []

    def scan_log_upsert(self, filename: str, entry: Dict[str, Any]) -> bool:
        if self.mock_mode:
            return True
        try:
            row = {
                "filename":    filename,
                "file_path":   entry.get("file_path", ""),
                "status":      entry.get("status", ""),
                "po_number":   entry.get("po_number", ""),
                "style_code":  entry.get("style_code", ""),
                "total_qty":   entry.get("total_qty") or 0,
                "trim_count":  entry.get("trim_count") or 0,
                "po_id":       entry.get("po_id"),
                "session_id":  entry.get("session_id"),
                "timestamp":   entry.get("timestamp", ""),
                "warning":     entry.get("warning", ""),
                "error_msg":   entry.get("error", ""),
            }
            self.client.table("scan_log").upsert(row, on_conflict="filename").execute()
            return True
        except Exception as e:
            logger.error(f"scan_log_upsert error: {e}")
            return False

    def scan_log_delete(self, filename: str) -> bool:
        if self.mock_mode:
            return True
        try:
            self.client.table("scan_log").delete().eq("filename", filename).execute()
            return True
        except Exception as e:
            logger.error(f"scan_log_delete error: {e}")
            return False

    # ── upload_history (trang Upload File thủ công) ───────────────────────────

    def upload_history_insert(self, entry: Dict[str, Any]) -> bool:
        """Lưu một lần xử lý từ trang Upload File."""
        if self.mock_mode:
            logger.info(f"[Mock] upload_history_insert: {entry.get('filename')}")
            return True
        try:
            row = {
                "filename":   entry.get("filename", ""),
                "status":     entry.get("status", ""),
                "po_number":  entry.get("po_number") or "",
                "style_code": entry.get("style_code") or "",
                "total_qty":  entry.get("total_qty") or 0,
                "trim_count": entry.get("trim_count") or 0,
                "timestamp":  entry.get("timestamp") or "",
                "warning":    entry.get("warning") or "",
                "error_msg":  entry.get("error") or "",
                "has_techpack": bool(entry.get("has_techpack")),
                "source":     "upload_file",
            }
            self.client.table("upload_history").insert(row).execute()
            return True
        except Exception as e:
            logger.error(f"upload_history_insert error: {e}")
            return False

    def upload_history_get(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy lịch sử upload, mới nhất trước."""
        if self.mock_mode:
            return []
        try:
            resp = (
                self.client.table("upload_history")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"upload_history_get error: {e}")
            return []

    # ── task_a_history (PO ↔ GO Compare) ──────────────────────────────────────

    def task_a_history_upsert(self, entry: Dict[str, Any]) -> bool:
        """Lưu/cập nhật một lần chạy Task A. Upsert theo token: bước generate rồi
        compare dùng chung token → gộp vào một dòng thay vì tạo trùng."""
        if self.mock_mode:
            logger.info(f"[Mock] task_a_history_upsert: {entry.get('token')}")
            return True
        try:
            row = {
                "token":          entry.get("token", ""),
                "status":         entry.get("status", "partial"),
                "file_name":      entry.get("file_name") or "",
                "po_number":      entry.get("po_number") or "",
                "style_code":     entry.get("style_code") or "",
                "qty":            entry.get("qty") or 0,
                "compared":       entry.get("compared") or 0,
                "go_source":      entry.get("go_source") or "",
                "batch_go_token": entry.get("batch_go_token") or "",
                "report_token":   entry.get("report_token") or "",
                "alerts_token":   entry.get("alerts_token") or "",
                "warning":        entry.get("warning") or "",
                "error_msg":      entry.get("error") or "",
            }
            self.client.table("task_a_history").upsert(row, on_conflict="token").execute()
            return True
        except Exception as e:
            logger.error(f"task_a_history_upsert error: {e}")
            return False

    def task_a_history_get(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy lịch sử Task A, mới nhất trước."""
        if self.mock_mode:
            return []
        try:
            resp = (
                self.client.table("task_a_history")
                .select("*").order("created_at", desc=True).limit(limit).execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"task_a_history_get error: {e}")
            return []

    # ── task_b_history (Generate Trimlist) ────────────────────────────────────

    def task_b_history_upsert(self, entry: Dict[str, Any]) -> bool:
        """Lưu một lần tạo Trimlist (Task B). Upsert theo token (= excel_token)."""
        if self.mock_mode:
            logger.info(f"[Mock] task_b_history_upsert: {entry.get('token')}")
            return True
        try:
            row = {
                "token":      entry.get("token", ""),
                "status":     entry.get("status", "success"),
                "file_name":  entry.get("file_name") or "",
                "po_number":  entry.get("po_number") or "",
                "style_code": entry.get("style_code") or "",
                "qty":        entry.get("qty") or 0,
                "item_count": entry.get("item_count") or 0,
                "warning":    entry.get("warning") or "",
                "error_msg":  entry.get("error") or "",
            }
            self.client.table("task_b_history").upsert(row, on_conflict="token").execute()
            return True
        except Exception as e:
            logger.error(f"task_b_history_upsert error: {e}")
            return False

    def task_b_history_get(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy lịch sử Task B, mới nhất trước."""
        if self.mock_mode:
            return []
        try:
            resp = (
                self.client.table("task_b_history")
                .select("*").order("created_at", desc=True).limit(limit).execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"task_b_history_get error: {e}")
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
