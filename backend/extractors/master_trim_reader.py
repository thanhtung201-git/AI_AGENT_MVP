"""
master_trim_reader.py — Đọc file Trim Master Excel bất kỳ.

Không hardcode tên sheet, tên cột, hay cấu trúc file.
LLM tự detect sheet phù hợp và parse cột dựa vào header thực tế.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from tools.excel_reader import read_excel_structured

logger = logging.getLogger(__name__)


def _looks_like_style(v: str) -> bool:
    """Article-code shaped token (mixes letters+digits, len>=5) — e.g. HSSH2AC12."""
    s = str(v or "").strip()
    return len(s) >= 5 and any(c.isalpha() for c in s) and any(c.isdigit() for c in s) and " " not in s


def _sheet_matches_branch(sheet_name: str, branch_key: str) -> bool:
    """Deterministic: does this sheet belong to the branch (gender × construction)?
    Handles the "women contains men" trap."""
    n = (sheet_name or "").lower()
    b = (branch_key or "").lower()
    gender = next((g for g in ("men", "ladies", "kids") if g in b), None)
    constr = next((c for c in ("woven", "knit") if c in b), None)
    if not gender or not constr:
        return False
    if gender == "men":
        gender_ok = bool(re.search(r"\bmen\b", n)) and "women" not in n
    elif gender == "ladies":
        gender_ok = "ladies" in n or "women" in n
    else:
        gender_ok = "kids" in n or "child" in n
    return gender_ok and constr in n


class MasterTrimReader:
    """
    Đọc Trim Master Excel của bất kỳ khách hàng nào.
    Không giả định tên sheet, tên cột, hay số cột.
    LLM chọn sheet đúng và map column.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path

    def read(self, garment_type: str = "") -> Dict[str, Any]:
        """
        Đọc trim list từ Trim Master.

        Args:
            garment_type: gợi ý loại hàng (vd "Men Woven", "Jacket", "Knitwear"...)
                          LLM sẽ dùng gợi ý này để chọn sheet phù hợp nhất.
                          Nếu rỗng → đọc sheet đầu tiên hoặc sheet duy nhất.

        Returns:
            {"success": bool, "sheet": str, "items": list[dict], "error": str|None}
        """
        # Đọc toàn bộ file (tất cả sheets)
        structured = read_excel_structured(self.file_path)
        if not structured.get("success"):
            return {"success": False, "sheet": "", "items": [],
                    "error": structured.get("error", "Không đọc được file Excel")}

        all_sheets = structured.get("structured", [])
        if not all_sheets:
            return {"success": False, "sheet": "", "items": [],
                    "error": "File Excel không có sheet nào"}

        # Chọn sheet phù hợp
        sheet_data = self._select_sheet(all_sheets, garment_type)
        if not sheet_data:
            return {"success": False, "sheet": "", "items": [],
                    "error": f"Không tìm được sheet phù hợp cho garment type: '{garment_type}'"}

        sheet_name = sheet_data["name"]
        logger.info(f"MasterTrimReader: đọc sheet '{sheet_name}' từ {self.file_path}")

        items = self._parse_sheet_with_llm(sheet_data, sheet_name)
        logger.info(f"MasterTrimReader: {len(items)} items từ sheet '{sheet_name}'")

        return {"success": True, "sheet": sheet_name, "items": items, "error": None}

    def detect_branch_by_codes(self, techpack_text: str) -> Dict[str, Any]:
        """
        Deterministic branch vote: the Tech Pack quotes real material codes
        (e.g. an RFID code, a button-bag code). Each Trim Master sheet carries the
        codes of ITS branch — so the branch whose codes actually appear in the
        Tech Pack text is the branch of this order. No gender keywords needed,
        no LLM, no customer hardcode.

        Returns {"branch": str|None, "score": int, "scores": {branch: n}}.
        """
        empty = {"branch": None, "score": 0, "scores": {}}
        if not techpack_text:
            return empty
        structured = read_excel_structured(self.file_path)
        if not structured.get("success"):
            return empty

        tp_tokens = {
            t for t in re.findall(r"[A-Za-z0-9]{7,}", techpack_text.lower())
            if sum(c.isdigit() for c in t) >= 4
        }
        scores: Dict[str, int] = {}
        for sheet in structured.get("structured", []):
            # "Ladies Woven (1)" / "(2)" belong to one branch — strip the suffix.
            branch = re.sub(r"\s*\(\d+\)\s*$", "", sheet["name"]).strip()
            codes = set()
            for row in sheet.get("rows", []):
                for cell in row.get("cells", []):
                    for t in re.findall(r"[A-Za-z0-9]{7,}", str(cell.get("value", "")).lower()):
                        if sum(c.isdigit() for c in t) >= 4:
                            codes.add(t)
            scores[branch] = scores.get(branch, 0) + len(codes & tp_tokens)

        if not scores:
            return empty
        best = max(scores, key=lambda k: scores[k])
        others = [v for k, v in scores.items() if k != best]
        # A clear winner needs evidence AND a strict lead — shared codes (both
        # branches stock the same polybag) push every score up together.
        if scores[best] >= 2 and scores[best] > max(others, default=0):
            logger.info(f"detect_branch_by_codes: '{best}' wins {scores}")
            return {"branch": best, "score": scores[best], "scores": scores}
        logger.info(f"detect_branch_by_codes: no clear winner {scores}")
        return {"branch": None, "score": scores[best], "scores": scores}

    def read_branch(self, branch_key: str) -> Dict[str, Any]:
        """
        Deterministically select the branch's BASE trim sheet + its EXCEPTION sheet.

        A branch (e.g. "Ladies Woven") may map to 2 sheets:
          - BASE      : the real trim list (has ITEM/CODE/SUPPLIER columns)
          - EXCEPTION : style-based rules (Style No list + reminder text, no code cols)
        We tell them apart by COLUMN STRUCTURE — not by the "(1)/(2)" in the name — so
        it generalises to any brand.

        Returns:
          {success, branch, base_sheet, items, exception_sheet, exceptions:{styles,reminders}, error}
        """
        structured = read_excel_structured(self.file_path)
        if not structured.get("success"):
            return {"success": False, "error": structured.get("error"), "items": []}

        all_sheets = structured.get("structured", [])
        matching = [s for s in all_sheets if _sheet_matches_branch(s["name"], branch_key)]

        if not matching:
            # No branch match → fall back to the legacy single-sheet selection.
            logger.warning(f"read_branch: no sheet matches '{branch_key}', falling back to read()")
            legacy = self.read(branch_key)
            return {"success": legacy.get("success"), "branch": branch_key,
                    "base_sheet": legacy.get("sheet"), "items": legacy.get("items", []),
                    "exception_sheet": None, "exceptions": {"styles": [], "reminders": []},
                    "error": legacy.get("error")}

        base_sheet = exc_sheet = None
        for s in matching:
            kind = self._classify_sheet(s["rows"])
            if kind == "base" and base_sheet is None:
                base_sheet = s
            elif kind == "exception" and exc_sheet is None:
                exc_sheet = s
        if base_sheet is None:
            base_sheet = matching[0]

        items      = self._parse_sheet_with_llm(base_sheet, base_sheet["name"])
        exceptions = self._parse_exception_sheet(exc_sheet) if exc_sheet else {"styles": [], "reminders": []}

        logger.info(
            f"read_branch '{branch_key}': base='{base_sheet['name']}' ({len(items)} items), "
            f"exception='{exc_sheet['name'] if exc_sheet else None}' "
            f"({len(exceptions['styles'])} styles, {len(exceptions['reminders'])} reminders)"
        )
        return {"success": True, "branch": branch_key, "base_sheet": base_sheet["name"],
                "items": items, "exception_sheet": exc_sheet["name"] if exc_sheet else None,
                "exceptions": exceptions, "error": None}

    @staticmethod
    def _classify_sheet(rows: List[Dict]) -> str:
        """'base' (trim list with code/supplier cols) vs 'exception' (style + reminders)."""
        header_blob = " ".join(
            c["value"].lower() for r in rows[:6] for c in r.get("cells", [])
        )
        has_supplier = "supplier" in header_blob
        has_code     = bool(re.search(r"\bcode\b", header_blob))
        has_item     = bool(re.search(r"\bitem\b|description", header_blob))
        if (has_supplier or has_code) and has_item:
            return "base"

        col_a = [c["value"] for r in rows for c in r.get("cells", []) if c.get("col_letter") == "A"]
        code_like = sum(1 for v in col_a if _looks_like_style(v))
        has_reminder = "reminder" in header_blob or "style no" in header_blob
        if has_reminder or (col_a and code_like / len(col_a) > 0.4):
            return "exception"
        return "base"

    @staticmethod
    def _parse_exception_sheet(sheet: Dict) -> Dict[str, List[str]]:
        """Pull style codes + reminder sentences from an exception sheet."""
        styles, reminders = [], []
        for r in sheet.get("rows", []):
            for c in r.get("cells", []):
                v = str(c.get("value", "")).strip()
                if not v:
                    continue
                if _looks_like_style(v):
                    styles.append(v)
                elif len(v.split()) >= 4:   # a sentence-like reminder
                    reminders.append(v)
        return {"styles": sorted(set(styles)), "reminders": reminders}

    def read_all_sheets(self) -> Dict[str, Any]:
        """Đọc tất cả sheets, trả về dict {sheet_name: items}."""
        structured = read_excel_structured(self.file_path)
        if not structured.get("success"):
            return {"success": False, "sheets": {}, "error": structured.get("error")}

        sheets = {}
        for sheet_data in structured.get("structured", []):
            name = sheet_data["name"]
            items = self._parse_sheet_with_llm(sheet_data, name)
            if items:
                sheets[name] = items

        return {"success": True, "sheets": sheets, "error": None}

    # ── Internal ──────────────────────────────────────────────────────────────

    def _select_sheet(self, all_sheets: list, garment_type: str) -> Optional[Dict]:
        """
        Chọn sheet phù hợp nhất với garment_type.
        Nếu chỉ có 1 sheet → dùng ngay.
        Nếu không có garment_type → gộp TẤT CẢ sheets vào 1 sheet ảo.
        Nếu có garment_type → LLM chọn sheet đúng.
        """
        if len(all_sheets) == 1:
            return all_sheets[0]

        if not garment_type:
            # Merge all sheets into one virtual sheet to maximize coverage
            return self._merge_all_sheets(all_sheets)

        sheet_names = [s["name"] for s in all_sheets]

        # LLM chọn sheet
        chosen_name = self._llm_select_sheet(sheet_names, garment_type)
        if chosen_name:
            for s in all_sheets:
                if s["name"] == chosen_name:
                    return s

        # Fallback: tìm sheet có tên gần nhất (case-insensitive substring)
        gt_lower = garment_type.lower()
        for s in all_sheets:
            if gt_lower in s["name"].lower() or s["name"].lower() in gt_lower:
                return s

        # Last resort: merge all
        return self._merge_all_sheets(all_sheets)

    def _merge_all_sheets(self, all_sheets: list) -> Dict:
        """Gộp tất cả sheets thành 1 sheet ảo (maximise coverage)."""
        merged_rows = []
        for s in all_sheets:
            merged_rows.extend(s.get("rows", []))
        return {"name": "ALL_SHEETS", "rows": merged_rows}

    def _llm_select_sheet(self, sheet_names: List[str], garment_type: str) -> Optional[str]:
        """Dùng LLM để chọn tên sheet phù hợp nhất."""
        try:
            from backend.utils.groq_client import GroqClient
            llm = GroqClient()

            system = "You are a garment production assistant. Return valid JSON only."
            prompt = f"""A Trim Master Excel file has these sheets:
{chr(10).join(f'- {n}' for n in sheet_names)}

The user is working on garment type: "{garment_type}"

Which sheet name best matches this garment type?
Return JSON: {{"chosen_sheet": "<exact sheet name from the list above>"}}
If no sheet is relevant, return {{"chosen_sheet": null}}"""

            result = llm.extract_json(system_prompt=system, user_content=prompt)
            if isinstance(result, dict):
                chosen = result.get("chosen_sheet")
                if chosen and chosen in sheet_names:
                    logger.info(f"MasterTrimReader: LLM chọn sheet '{chosen}'")
                    return chosen
        except Exception as e:
            logger.warning(f"MasterTrimReader: LLM sheet selection error: {e}")
        return None

    def _parse_sheet_with_llm(self, sheet_data: Dict, sheet_name: str) -> List[Dict]:
        """
        Parse rows từ một sheet.
        Detect header bằng LLM, sau đó extract từng row.
        """
        rows = sheet_data.get("rows", [])
        if not rows:
            return []

        # Lấy tối đa 3 rows đầu để detect header
        sample_rows = rows[:5]
        sample_text = self._rows_to_text(sample_rows)

        col_map = self._llm_detect_columns(sample_text, sheet_name)
        if not col_map:
            logger.warning(f"MasterTrimReader: không detect được columns trong sheet '{sheet_name}'")
            return []

        logger.info(f"MasterTrimReader: col_map = {col_map}")
        return self._extract_rows(rows, col_map, sheet_name)

    def _llm_detect_columns(self, sample_text: str, sheet_name: str) -> Optional[Dict]:
        """
        Dùng LLM để detect column mapping từ header rows thực tế.
        Trả về {"item": "A", "code": "C", "supplier": "D", "qty": "E", "remark": "F"}
        """
        try:
            from backend.utils.groq_client import GroqClient
            llm = GroqClient()

            system = "You are a spreadsheet parser. Return valid JSON only."
            prompt = f"""These are the first rows of a Trim Master Excel sheet named "{sheet_name}":

{sample_text}

Identify which column letter contains each of these fields:
- item_name: the trim/material item description
- material_code: the material code or item code (e.g. product number, article code)
- supplier: the supplier or vendor name
- qty: quantity per garment (consumption)
- remark: notes or remarks

Return JSON:
{{
  "item_name": "<column letter or null>",
  "material_code": "<column letter or null>",
  "supplier": "<column letter or null>",
  "qty": "<column letter or null>",
  "remark": "<column letter or null>",
  "header_row_index": <0-based row index of the header row, or 0 if first row is data>
}}

Rules:
- Use the EXACT column letter from the data (A, B, C, D...)
- If a field is not present, return null for that field
- Do not guess — only map columns that clearly match"""

            result = llm.extract_json(system_prompt=system, user_content=prompt)
            if isinstance(result, dict) and result.get("item_name"):
                return result
        except Exception as e:
            logger.warning(f"MasterTrimReader: LLM column detect error: {e}")

        # Fallback: scan rows for common header keywords
        return self._fallback_detect_columns(sample_text)

    def _fallback_detect_columns(self, sample_text: str) -> Optional[Dict]:
        """Detect columns bằng keyword matching khi LLM fail."""
        # Parse sample_text back to understand structure
        # sample_text format: "Row N: A=val | B=val | ..."
        import re
        col_map = {"item_name": None, "material_code": None, "supplier": None,
                   "qty": None, "remark": None, "header_row_index": 0}

        for line in sample_text.splitlines():
            if not line.strip():
                continue
            # Look for header keywords
            parts = re.findall(r'([A-Z]+)=([^|]+)', line)
            for col_letter, val in parts:
                v = val.strip().lower()
                if any(k in v for k in ["item", "material", "trim", "description"]) and not col_map["item_name"]:
                    col_map["item_name"] = col_letter
                elif any(k in v for k in ["code", "article", "ref", "number"]) and not col_map["material_code"]:
                    col_map["material_code"] = col_letter
                elif "supplier" in v and not col_map["supplier"]:
                    col_map["supplier"] = col_letter
                elif any(k in v for k in ["qty", "quantity", "consumption"]) and not col_map["qty"]:
                    col_map["qty"] = col_letter
                elif "remark" in v and not col_map["remark"]:
                    col_map["remark"] = col_letter

        return col_map if col_map.get("item_name") else None

    def _rows_to_text(self, rows: List[Dict]) -> str:
        """Convert row dicts to readable text for LLM."""
        lines = []
        for i, row in enumerate(rows):
            cells = {c["col_letter"]: str(c["value"]).strip() for c in row.get("cells", []) if c.get("value") not in (None, "", "None")}
            if cells:
                cell_str = " | ".join(f"{k}={v}" for k, v in cells.items())
                lines.append(f"Row {i}: {cell_str}")
        return "\n".join(lines)

    def _extract_rows(self, rows: List[Dict], col_map: Dict, sheet_name: str = "") -> List[Dict]:
        """Extract items từ rows dựa vào col_map. Bắt kèm toạ độ (sheet!cell) để deep-link."""
        header_row_idx = col_map.get("header_row_index", 0)
        if isinstance(header_row_idx, str):
            try:
                header_row_idx = int(header_row_idx)
            except ValueError:
                header_row_idx = 0

        item_col     = col_map.get("item_name")
        code_col     = col_map.get("material_code")
        supplier_col = col_map.get("supplier")
        qty_col      = col_map.get("qty")
        remark_col   = col_map.get("remark")

        items = []
        for row in rows[header_row_idx + 1:]:
            cells = {c["col_letter"]: str(c["value"]).strip() for c in row.get("cells", []) if c.get("value") not in (None, "", "None")}
            if not cells:
                continue

            item_name = cells.get(item_col, "").strip() if item_col else ""
            # Try col A as fallback for item name
            if not item_name:
                item_name = cells.get("A", "").strip()
            if not item_name:
                continue

            code     = cells.get(code_col, "").strip() if code_col else ""
            supplier = cells.get(supplier_col, "").strip() if supplier_col else ""
            qty_str  = cells.get(qty_col, "").strip() if qty_col else ""
            remark   = cells.get(remark_col, "").strip() if remark_col else ""

            if not code and not supplier:
                continue  # skip rows với không có thông tin

            # Exact source location — the code cell if we have one, else item cell.
            row_num  = row.get("row")
            loc_col  = code_col if (code_col and code) else (item_col or "A")
            cell_ref = f"{loc_col}{row_num}" if row_num else ""

            items.append({
                "trim_item":       item_name,
                "supplier_code":   code,        # material code (e.g. FT770ES, 220019916X)
                "supplier":        supplier,
                "qty_per_garment": self._parse_qty(qty_str),
                "unit":            self._parse_unit(qty_str),
                "remark":          remark,
                "category":        "",          # category sẽ do LLM classify trong TrimMasterMapper
                "source":          "master_trim",
                "_loc":            {"file": "master", "sheet": sheet_name, "cell": cell_ref, "row": row_num},
            })

        return items

    def _parse_qty(self, qty_str: str) -> float:
        import re
        m = re.search(r"[\d.]+", qty_str or "")
        return float(m.group()) if m else 1.0

    def _parse_unit(self, qty_str: str) -> str:
        import re
        m = re.search(r"(pcs?|ea|pc|set|roll|m\b|cm\b|yds?|cone|kg)", (qty_str or "").lower())
        return m.group() if m else "pcs"
