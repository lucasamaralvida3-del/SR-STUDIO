from __future__ import annotations

"""Shared supervised semantic vocabulary for G2 product-card recovery.

The rules here are intentionally structural and source-compatible.  Units are
canonical semantic tokens; their literal spelling is preserved by the template
binding layer.  Promotion/club labels are independent roles and must never be
used as product names.
"""

import re
import unicodedata

UNIT_RE = re.compile(r"^/?(?:KG|UN|UND|UNID(?:ADE)?|G|L|ML|LT|CX|PCT|PC|BDJ|CADA|QUILO)$", re.IGNORECASE)
CURRENCY_RE = re.compile(r"^R\s*\$$", re.IGNORECASE)

_PROMOTION_CANONICAL = {
    "PROMOCAO",
    "NA PROMOCAO",
    "EM PROMOCAO",
    "PRECO PROMOCIONAL",
    "OFERTA",
    "OFERTA ESPECIAL",
}
_CLUB_CANONICAL = {
    "NO SR CLUBE SMART",
    "NO SRCLUBE",
    "NO SR CLUBE",
    "NO CLUBE SR",
    "CLUBE SR",
    "CLUBE SMART",
    "SR CLUBE SMART",
}


def canonical_text(value: str) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split()).strip().upper()
    text = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
    return text


def is_unit_text(value: str) -> bool:
    return bool(UNIT_RE.fullmatch(" ".join(str(value or "").split()).strip()))


def semantic_label_role(value: str) -> str:
    normalized = canonical_text(value)
    compact = normalized.replace(" ", "")
    if normalized in _PROMOTION_CANONICAL or normalized.startswith("PROMOCAO ") or normalized.endswith(" PROMOCAO"):
        return "promotion"
    if normalized in _CLUB_CANONICAL or "CLUBE" in normalized and ("SR" in normalized or "SMART" in normalized):
        return "club_label"
    if compact in {"NOSRCLUBE", "NOSRCLUBESMART", "NOCLUBESR"}:
        return "club_label"
    return ""


def is_semantic_label(value: str) -> bool:
    return bool(semantic_label_role(value))


def is_name_forbidden_token(value: str) -> bool:
    text = " ".join(str(value or "").split()).strip()
    return bool(CURRENCY_RE.fullmatch(text) or is_unit_text(text) or is_semantic_label(text))
