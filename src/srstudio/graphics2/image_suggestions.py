from __future__ import annotations

"""Conservative, display-only ranking for spreadsheet product photographs."""

import re
import unicodedata
from typing import Any


def _plain(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").upper())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _code(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _plain(value))


def _measure(text: str) -> tuple[str, int] | None:
    match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(KG|G|ML|L)\b", text)
    if not match:
        return None
    amount = float(match.group(1).replace(",", "."))
    unit = match.group(2)
    return ("mass" if unit in {"KG", "G"} else "volume",
            round(amount * 1000) if unit in {"KG", "L"} else round(amount))


def _values(item: dict[str, Any], keys: tuple[str, ...]) -> set[str]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return {_code(source.get(key)) for source in (item, metadata) for key in keys
            if source.get(key) not in (None, "")} - {""}


def score_image_candidate(product: dict[str, Any], image: dict[str, Any]) -> dict[str, Any]:
    """Explain a suggestion; never return an instruction to bind the image."""
    if image.get("kind") not in {"product", "unknown"}:
        return {"score": 0, "reason": "Imagem decorativa"}
    p_ean = _values(product, ("ean", "gtin", "barcode", "cod_barras"))
    i_ean = _values(image, ("ean", "gtin", "barcode", "cod_barras"))
    p_code = _values(product, ("id", "product_id", "code", "sku"))
    i_code = _values(image, ("product_id", "code", "sku", "product_code"))
    if p_ean and i_ean and not p_ean.intersection(i_ean):
        return {"score": 0, "reason": "EAN/GTIN diferente"}
    same_ean = bool(p_ean and i_ean and p_ean.intersection(i_ean))
    if p_code and i_code and not p_code.intersection(i_code) and not same_ean:
        return {"score": 0, "reason": "Código interno diferente"}
    p_name = _plain(product.get("name") or product.get("display_name") or product.get("original_name"))
    i_name = _plain(image.get("name") or image.get("product_name"))
    p_measure = _measure(p_name + " " + _plain(product.get("weight") or product.get("volume")))
    i_measure = _measure(i_name + " " + _plain(image.get("weight") or image.get("volume")))
    if p_measure and i_measure and p_measure != i_measure:
        return {"score": 0, "reason": "Peso ou volume diferente"}
    p_brand = _plain(product.get("brand") or product.get("marca")).strip()
    i_brand = _plain(image.get("brand") or image.get("marca")).strip()
    if p_brand and i_brand and p_brand != i_brand:
        return {"score": 0, "reason": "Marca diferente"}
    if same_ean:
        score, reason = 100, "EAN/GTIN correspondente"
    elif p_code and i_code and p_code.intersection(i_code):
        score, reason = 90, "Código interno correspondente"
    elif p_name and i_name and p_name == i_name:
        score, reason = 75, "Descrição correspondente"
    else:
        p_words = {word for word in re.findall(r"[A-Z0-9]+", p_name) if len(word) >= 4}
        i_words = {word for word in re.findall(r"[A-Z0-9]+", i_name) if len(word) >= 4}
        common = p_words & i_words
        if len(common) < 2:
            return {"score": 0, "reason": "Sem evidência suficiente"}
        score, reason = min(60, 15 * len(common)), "Descrição semelhante; confira a embalagem"
    if p_brand and i_brand:
        score += 3
    if p_measure and i_measure:
        score += 3
    return {"score": min(score, 100), "reason": reason,
            "requires_confirmation": True}


def suggest_product_images(product: dict[str, Any], images: list[dict[str, Any]],
                           *, limit: int = 50) -> list[dict[str, Any]]:
    ranked = []
    for image in images:
        match = score_image_candidate(product, image)
        if match["score"]:
            ranked.append({**image, **match})
    ranked.sort(key=lambda item: (-item["score"], str(item.get("name", "")).casefold(),
                                  str(item.get("id", ""))))
    return ranked[:limit]


def image_review_states(products: list[dict[str, Any]],
                        images: list[dict[str, Any]]) -> dict[str, str]:
    """Classify spreadsheet items while indexing the bank once per refresh."""
    by_code: dict[str, set[int]] = {}
    by_ean: dict[str, set[int]] = {}
    by_word: dict[str, set[int]] = {}
    for index, image in enumerate(images):
        for code in _values(image, ("product_id", "code", "sku", "product_code")):
            by_code.setdefault(code, set()).add(index)
        for ean in _values(image, ("ean", "gtin", "barcode", "cod_barras")):
            by_ean.setdefault(ean, set()).add(index)
        for word in set(re.findall(r"[A-Z0-9]{4,}", _plain(image.get("name")))):
            by_word.setdefault(word, set()).add(index)
    states = {}
    for product in products:
        key = str(product.get("id") or product.get("product_id") or "")
        if not key:
            continue
        if product.get("image_path") or product.get("image"):
            states[key] = "linked"
            continue
        choices: set[int] = set()
        for code in _values(product, ("id", "product_id", "code", "sku")):
            choices.update(by_code.get(code, ()))
        for ean in _values(product, ("ean", "gtin", "barcode", "cod_barras")):
            choices.update(by_ean.get(ean, ()))
        for word in set(re.findall(r"[A-Z0-9]{4,}", _plain(product.get("name")))):
            choices.update(by_word.get(word, ()))
        states[key] = ("pending" if any(score_image_candidate(product, images[i])["score"]
                                       for i in choices) else "missing")
    return states
