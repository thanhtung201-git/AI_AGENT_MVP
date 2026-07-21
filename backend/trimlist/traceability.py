"""
traceability.py — Core data structures for Trimlist pipeline.

Every field in a TrimRow must be traceable to one of:
  1. Tech Pack      → techpack_ref
  2. Trim Master    → master_ref
  3. Buyer Rule     → buyer_rule
  4. Email Note     → email_ref
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldSource:
    """Tracks the origin of a single field value."""
    value:       Any
    source_type: str        # "techpack" | "master" | "buyer_rule" | "email" | "derived"
    ref:         str = ""   # human-readable reference, e.g. "Page 18 BOM Row 5"


@dataclass
class TrimSource:
    """Full source traceability for one TrimRow."""
    techpack_ref: Optional[str] = None   # "Section 16, BOM Table Row 5"
    master_ref:   Optional[str] = None   # "Men Woven Row 12 — FT770ES Fusing"
    buyer_rule:   Optional[str] = None   # "Rule HAZZYS-001: DTM Thread"
    email_ref:    Optional[str] = None   # "Email: 'Use YKK zipper instead of SBS'"
    # Structured deep-link location (exact sheet+cell / page) for click-to-source.
    master_loc:   Optional[Dict[str, Any]] = None   # {"file","sheet","cell","row"}

    def as_text(self) -> str:
        parts = []
        if self.techpack_ref: parts.append(f"TechPack: {self.techpack_ref}")
        if self.master_ref:   parts.append(f"TrimMaster: {self.master_ref}")
        if self.buyer_rule:   parts.append(f"BuyerRule: {self.buyer_rule}")
        if self.email_ref:    parts.append(f"Email: {self.email_ref}")
        return " | ".join(parts) if parts else "Unknown"

    def primary_source(self) -> str:
        """Returns the highest-priority source label."""
        if self.email_ref:    return "EMAIL"
        if self.buyer_rule:   return "BUYER_RULE"
        if self.master_ref:   return "TRIM_MASTER"
        if self.techpack_ref: return "TECH_PACK"
        return "UNKNOWN"


@dataclass
class TrimRow:
    """One row in the final Trimlist — all fields with source traceability."""

    # ── Classification ────────────────────────────────────────────────────────
    category:      str = "OTHER"      # FABRIC/YARN | INTERLINING | THREAD & BUTTON | LABEL | PACKING | OTHER
    sort_key:      int = 99           # for ordering within category

    # ── Identity ──────────────────────────────────────────────────────────────
    material_name: str = ""           # from Tech Pack (raw description)
    material_code: Optional[str] = None   # from Trim Master (e.g. FT770ES)

    # ── Sourcing ──────────────────────────────────────────────────────────────
    supplier:      Optional[str] = None
    supplier_code: Optional[str] = None   # vendor article code

    # ── Specification ─────────────────────────────────────────────────────────
    spec:          Optional[str] = None   # e.g. "Non-woven fusible, 75g/m2"

    # ── Usage ─────────────────────────────────────────────────────────────────
    placement:     Optional[str] = None   # e.g. "Front chest, collar stand"
    color:         Optional[str] = None   # e.g. "DTM", "White", "N2" (single colorway)
    colors:        Dict[str, str] = field(default_factory=dict)  # multi-colorway: {"N2": "Navy DTM", "W2": "White"}
    consumption:   Optional[str] = None   # e.g. "0.15 m/pc"
    unit:          str = "pcs"

    # ── Notes ─────────────────────────────────────────────────────────────────
    remark:        Optional[str] = None

    # ── Traceability ──────────────────────────────────────────────────────────
    source:        TrimSource = field(default_factory=TrimSource)

    # ── Validation ────────────────────────────────────────────────────────────
    alerts:        List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "category":      self.category,
            "material_name": self.material_name,
            "material_code": self.material_code,
            "supplier":      self.supplier,
            "supplier_code": self.supplier_code,
            "spec":          self.spec,
            "placement":     self.placement,
            "color":         self.color,
            "colors":        self.colors,
            "consumption":   self.consumption,
            "unit":          self.unit,
            "remark":        self.remark,
            "source":        self.source.as_text(),
            "source_detail": {
                "techpack_ref": self.source.techpack_ref,
                "master_ref":   self.source.master_ref,
                "buyer_rule":   self.source.buyer_rule,
                "email_ref":    self.source.email_ref,
                "master_loc":   self.source.master_loc,
            },
            "alerts":        self.alerts,
        }


# ── Category ordering (used for sorting in Excel) ────────────────────────────

CATEGORY_ORDER = {
    "FABRIC/YARN":     1,
    "INTERLINING":     2,
    "THREAD & BUTTON": 3,
    "LABEL":           4,
    "PACKING":         5,
    "OTHER":           6,
}

CATEGORY_KEYWORDS = {
    "FABRIC/YARN": [
        "fabric", "yarn", "lining", "linen", "lycra", "wool", "cotton",
        "polyester", "fleece", "rib", "elastic", "main fabric", "shell fabric",
        "body fabric", "woven", "knit", "twill", "oxford", "denim", "canvas",
    ],
    "INTERLINING": [
        "interlin", "interfacing", "fusible", "fusing", "weft insert",
        "non-woven", "nonwoven", "#dh", "#m13", "#ft", "chest piece",
        "collar canvas", "sleeve head", "wadding", "batting",
    ],
    "THREAD & BUTTON": [
        "thread", "sewing thread", "button", "bttn", "snap", "hook", "eye",
        "zipper", "zip", "drawcord", "cord", "tape", "ribbon", "braid",
        "velcro", "d-ring", "buckle", "ring", "slider",
    ],
    "LABEL": [
        "label", "care label", "main label", "size label", "hangtag",
        "hang tag", "main tag", "rfid", "price tag", "emb",
        "woven label", "point label", "embroidery", "patch", "badge",
        "heat transfer", "printed label",
    ],
    "PACKING": [
        "polybag", "poly bag", "carton", "cardboard", "silica gel",
        "tissue", "butterfly", "clip", "collarband", "collar band", "color band",
        "sealing", "product paper", "paper board", "stiffener", "insert",
        "hanger", "inner box", "master carton", "extra button", "button bag",
        "barcode", "sticker", "tag loop", "fastener", "verify", "verify sticker",
        "sticker mark", "adhesive tape", "plastic clip", "paper clip",
    ],
}


def classify_category(name: str) -> str:
    """Classify a trim item into its category by keyword.

    Longest-match wins: a more specific keyword outranks a shorter one, so
    "adhesive tape" → PACKING beats "tape" → THREAD & BUTTON, and "button bag"
    → PACKING beats "button" → THREAD & BUTTON. Ties fall to the earlier
    category (FABRIC → INTERLINING → THREAD → LABEL → PACKING).
    """
    name_lower = (name or "").lower()
    best_cat, best_len = "OTHER", 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower and len(kw) > best_len:
                best_cat, best_len = category, len(kw)
    return best_cat
