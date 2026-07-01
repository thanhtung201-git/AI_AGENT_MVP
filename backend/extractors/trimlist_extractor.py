import json
import logging
from typing import List, Dict, Any
from backend.utils.groq_client import GroqClient
from backend.utils.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class TrimlistExtractor:
    """Trích xuất danh sách trim/phụ liệu từ text techpack dùng Groq LLM."""

    def __init__(self):
        self.groq_client = GroqClient()
        self.system_prompt = PromptManager.load_prompt("trimlist_prompt.txt")
        self.header_prompt = PromptManager.load_prompt("techpack_header_prompt.txt")

    def extract_header(self, raw_text: str) -> Dict[str, Any]:
        """Dùng LLM đọc header/cover page của techpack — chính xác hơn regex."""
        # Chỉ gửi 3000 ký tự đầu (cover page)
        snippet = raw_text[:3000]
        try:
            result = self.groq_client.extract_json(
                system_prompt=self.header_prompt,
                user_content=snippet,
            )
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error(f"Header extraction error: {e}")
            return {}

    def extract(self, raw_text: str, order_qty: int = 0) -> List[Dict[str, Any]]:
        """
        Trích xuất trim items từ text techpack.
        Nếu order_qty > 0, tính thêm total_qty = qty_per_garment * order_qty.

        Returns:
            List[Dict] mỗi item có: trim_item, spec, supplier, supplier_code,
                                    placement, qty_per_garment, unit, total_qty
        """
        if not raw_text or not raw_text.strip():
            logger.warning("TrimlistExtractor: empty text.")
            return []

        try:
            # Chỉ xử lý chunk nào có khả năng chứa bảng BOM/Trim
            chunks = self._split_text(raw_text, max_chars=8000)
            bom_chunks = [c for c in chunks if self._looks_like_bom(c)]
            if not bom_chunks:
                # Fallback: dùng tất cả nếu không detect được
                bom_chunks = chunks
            logger.info(f"TrimlistExtractor: {len(bom_chunks)}/{len(chunks)} chunks có BOM table.")

            items = []
            for chunk in bom_chunks:
                result = self.groq_client.extract_json(
                    system_prompt=self.system_prompt,
                    user_content=chunk,
                )
                chunk_items = result if isinstance(result, list) else (
                    result.get("items") or result.get("trim_items") or []
                )
                items.extend(chunk_items)

            items = self._deduplicate(items)
            items = self._filter_valid(items)

            # Tính total_qty nếu có order_qty
            for item in items:
                qty_pg = item.get("qty_per_garment") or 0
                try:
                    qty_pg = float(qty_pg)
                except (TypeError, ValueError):
                    qty_pg = 0
                item["qty_per_garment"] = qty_pg
                item["total_qty"] = round(qty_pg * order_qty, 2) if order_qty > 0 else None

            logger.info(f"TrimlistExtractor: {len(items)} trim items extracted.")
            return items

        except Exception as e:
            msg = str(e)
            if "rate_limit" in msg.lower() or "429" in msg:
                import re
                wait = re.search(r"try again in ([\d\w\s\.]+)", msg)
                wait_str = wait.group(1).strip() if wait else "vài phút"
                raise RuntimeError(f"[RATE LIMIT] Hết token ngày. Vui lòng thử lại sau {wait_str}.") from e
            logger.error(f"TrimlistExtractor error: {e}")
            return []

    def _filter_valid(self, items: list) -> list:
        """Loại item rác: qty=0/null, tên rỗng."""
        result = []
        for it in items:
            qty = it.get("qty_per_garment")
            try:
                qty = float(qty or 0)
            except (TypeError, ValueError):
                qty = 0
            if qty <= 0:
                logger.info(f"Filter: bỏ '{it.get('trim_item')}' vì qty={qty}")
                continue
            if not str(it.get("trim_item", "")).strip():
                continue
            result.append(it)
        return result

    def _looks_like_bom(self, chunk: str) -> bool:
        """
        Phát hiện chunk có chứa bảng Trim hợp lệ.
        Ưu tiên: Section 16 (Expected Trim List) > Section 5 (Trim Spec).
        Bỏ qua chunk chỉ chứa Section 4 BOM overview.
        """
        import re
        text = chunk

        # Ưu tiên cao nhất: bảng "Expected Trim List" (section tổng hợp)
        if re.search(r"expected\s+trim\s+list", text, re.IGNORECASE):
            return True

        # Ưu tiên tiếp: "Trim Specification" table — có placement + supplier code
        if re.search(r"trim\s+specification", text, re.IGNORECASE):
            # Chỉ chấp nhận nếu thực sự có bảng (có cột PLACEMENT)
            return bool(re.search(r"\bplacement\b", text, re.IGNORECASE))

        # Loại bỏ chunk chỉ là BOM overview (không có placement, không có spec detail)
        has_bom = bool(re.search(r"bill\s+of\s+material", text, re.IGNORECASE))
        has_placement = bool(re.search(r"\bplacement\b", text, re.IGNORECASE))
        if has_bom and not has_placement:
            return False

        # Fallback: cần đủ 3 từ khóa bảng trim có placement
        keywords = [
            r"trim\s+(item|name|code)",
            r"supplier",
            r"qty|quantity",
            r"placement",
            r"supplier\s*code|trim\s*code",
        ]
        hits = sum(1 for p in keywords if re.search(p, text, re.IGNORECASE))
        return hits >= 3

    def _normalize_name(self, name: str) -> str:
        """Chuẩn hóa tên trim để so sánh: bỏ brackets, spec, dấu câu, lowercase."""
        import re
        name = re.sub(r"\[.*?\]", "", name)          # bỏ [JK-2201]
        name = re.sub(r"\(.*?\)", " ", name)          # bỏ (Main), (Pocket)
        name = re.sub(r"\d+\s*(cm|mm|m|l|pcs?)\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\b(ykk|vislon|coil|braided|round|metal|woven|dual.hole)\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"[^\w\s]", " ", name)          # bỏ dấu câu (, . - / ...)
        return re.sub(r"\s+", " ", name).strip().lower()

    def _score(self, item: dict) -> int:
        """Điểm số thông tin: item nào có nhiều field hơn thì giữ lại."""
        score = 0
        if item.get("supplier") and item["supplier"] not in ("None", "null", ""):
            score += 3
        if item.get("supplier_code") and item["supplier_code"] not in ("None", "null", ""):
            score += 2
        if item.get("placement") and item["placement"] not in ("None", "null", ""):
            score += 1
        if item.get("spec") and item["spec"] not in ("None", "null", ""):
            score += 1
        return score

    def _deduplicate(self, items: list, threshold: int = 75) -> list:
        """
        Loại bỏ trim trùng lặp theo 2 lớp:
        1. Exact match theo supplier_code (nếu có)
        2. Fuzzy match theo tên chuẩn hóa
        Giữ bản có điểm thông tin cao nhất.
        """
        try:
            from rapidfuzz import fuzz
            use_fuzzy = True
        except ImportError:
            use_fuzzy = False

        def _sup_root(s: str) -> str:
            """Lấy từ đầu của supplier để normalize 'YKK Vietnam Ltd.' vs 'YKK Vietnam'."""
            s = (s or "").lower().strip()
            return s.split()[0] if s else ""

        # Lớp 1: gộp theo supplier_code (exact)
        by_code: dict = {}
        no_code = []
        for item in items:
            code = (item.get("supplier_code") or "").strip()
            if code and code.lower() not in ("none", "null", "n/a", ""):
                if code not in by_code or self._score(item) > self._score(by_code[code]):
                    by_code[code] = item
            else:
                no_code.append(item)

        # Lớp 2: gộp theo (tên_chuẩn_hóa + supplier_root) cho items không có code
        # Bắt "Drawcord" từ Anjie ở chunk 1 vs chunk 4 — cùng tên, cùng supplier
        by_name_sup: dict = {}
        no_sup = []
        for item in no_code:
            name    = self._normalize_name(item.get("trim_item", ""))
            sup_key = _sup_root(item.get("supplier", ""))
            if not name:
                continue
            if sup_key:
                key = f"{name}|{sup_key}"
                if key not in by_name_sup or self._score(item) > self._score(by_name_sup[key]):
                    by_name_sup[key] = item
            else:
                no_sup.append(item)

        # Lớp 3: fuzzy name cho items còn lại (không có supplier)
        groups: list = []
        keys: list = []
        for item in no_sup:
            name = self._normalize_name(item.get("trim_item", ""))
            if not name:
                continue
            matched = False
            if use_fuzzy:
                for i, key in enumerate(keys):
                    if fuzz.token_sort_ratio(name, key) >= threshold:
                        groups[i].append(item)
                        matched = True
                        break
            if not matched:
                keys.append(name)
                groups.append([item])
        fuzzy_result = [max(g, key=self._score) for g in groups]

        # Gộp tất cả — loại trùng với coded items nếu tên tương đồng
        coded_items = list(by_code.values())
        coded_names = [self._normalize_name(it.get("trim_item", "")) for it in coded_items]

        merged = list(coded_items)
        for item in list(by_name_sup.values()) + fuzzy_result:
            name = self._normalize_name(item.get("trim_item", ""))
            if use_fuzzy and any(fuzz.token_sort_ratio(name, cn) >= threshold for cn in coded_names):
                continue
            merged.append(item)

        # Final pass: gộp theo (name + supplier_root + qty) để bắt items cùng tên/supplier
        # nhưng có supplier_code khác nhau giữa các chunk
        by_sig: dict = {}
        no_sig_final = []
        for item in merged:
            name    = self._normalize_name(item.get("trim_item", ""))
            sup_r   = _sup_root(item.get("supplier", ""))
            qty     = item.get("qty_per_garment") or 0
            if name and sup_r and qty:
                sig = f"{name}|{sup_r}|{qty}"
                if sig not in by_sig or self._score(item) > self._score(by_sig[sig]):
                    by_sig[sig] = item
            else:
                no_sig_final.append(item)
        final = list(by_sig.values()) + no_sig_final

        removed = len(items) - len(final)
        if removed:
            logger.info(f"Dedup: loại {removed} trim trùng, còn {len(final)} items.")
        return final

    def _deduplicate_exact(self, items: list) -> list:
        best: dict = {}
        for item in items:
            key = self._normalize_name(item.get("trim_item", ""))
            if not key:
                continue
            if key not in best or self._score(item) > self._score(best[key]):
                best[key] = item
        return list(best.values())

    def _split_text(self, text: str, max_chars: int = 8000):
        """Chia text thành chunks, ưu tiên cắt theo dòng trống."""
        if len(text) <= max_chars:
            return [text]
        chunks, current = [], ""
        for line in text.splitlines(keepends=True):
            if len(current) + len(line) > max_chars:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)
        return chunks
