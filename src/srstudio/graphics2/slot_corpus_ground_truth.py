from __future__ import annotations

"""Read-only supervised evidence extraction for real G2 flyer corpora.

This module does not detect ProductCards and does not mutate SR Scene.  It
serializes the semantic result already produced by GraphicsImportService into a
stable dataset that can be compared with real Canva/PPTX layouts.  That keeps
corpus learning separate from rendering and from the Image DB persistence
layer while still reusing ProductCards, PriceBlocks and Smart Slots.
"""

from hashlib import sha256
import json
from typing import Any, Iterable

from srstudio.images.association import normalize_product_name

from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, Rect, SmartSlot

SCHEMA = "srstudio/g2-slot-corpus-ground-truth/1"

_PRICE_BINDINGS = (
    BindingRole.CURRENCY.value,
    BindingRole.PRICE_REAIS.value,
    BindingRole.PRICE_CENTS.value,
    BindingRole.UNIT.value,
    BindingRole.RETAIL_PRICE.value,
)

_PROMOTION_ROLE_TOKENS = ("promotion", "promo", "oferta")
_CLUB_ROLE_TOKENS = ("club", "clube", "app_price", "app_unit")


def extract_slot_corpus_ground_truth(
    document: GraphicsDocument,
    *,
    source_name: str = "",
    source_sha256: str = "",
) -> dict[str, Any]:
    """Serialize current semantic ProductCards as supervised corpus evidence.

    Geometry is emitted both in document coordinates and relative to the
    ProductCard.  Family signatures intentionally exclude product category,
    product text and UNIT value: KG/UN/CADA/QUILO therefore remain the same
    structural family when their visual geometry is equivalent.
    """

    examples: list[dict[str, Any]] = []
    associations: list[dict[str, Any]] = []
    family_members: dict[str, list[str]] = {}

    for page_index, page in enumerate(document.pages, start=1):
        for slot in sorted(page.slots.values(), key=lambda item: item.id):
            example = _slot_evidence(
                document,
                page,
                slot,
                page_index=page_index,
                source_name=source_name,
                source_sha256=source_sha256,
            )
            if example is None:
                continue
            examples.append(example)
            family_members.setdefault(example["family_id"], []).append(example["example_id"])
            association = example.get("product_image_association")
            if isinstance(association, dict) and association.get("normalized_name"):
                associations.append(association)

    families = [
        {
            "family_id": family_id,
            "count": len(member_ids),
            "example_ids": member_ids,
            "signature": next(
                item["family_signature"]
                for item in examples
                if item["family_id"] == family_id
            ),
        }
        for family_id, member_ids in sorted(family_members.items())
    ]

    return {
        "schema": SCHEMA,
        "source": {
            "name": source_name,
            "sha256": source_sha256,
            "document_id": document.id,
            "document_name": document.name,
        },
        "pages_analyzed": len(document.pages),
        "product_cards": len(examples),
        "slot_families": len(families),
        "families": families,
        "examples": examples,
        "product_image_associations": associations,
    }


def _slot_evidence(
    document: GraphicsDocument,
    page: GraphicsPage,
    slot: SmartSlot,
    *,
    page_index: int,
    source_name: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    blocks = page.metadata.get("semantic_blocks")
    blocks = blocks if isinstance(blocks, dict) else {}
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    card = blocks.get(card_id) if card_id else None
    card = card if isinstance(card, dict) else None

    source_node_ids = _source_node_ids(page, slot, card)
    card_bounds = _card_bounds(page, slot, card, source_node_ids)
    if card_bounds is None or card_bounds.width <= 0 or card_bounds.height <= 0:
        return None

    image_ids = _binding_ids(page, slot, card, (BindingRole.IMAGE.value, "image"))
    name_ids = _binding_ids(page, slot, card, (BindingRole.NAME.value, "name"))
    unit_ids = _binding_ids(page, slot, card, (BindingRole.UNIT.value, "unit", "app_unit"))
    promotion_ids = _token_role_ids(page, slot, card, _PROMOTION_ROLE_TOKENS)
    club_ids = _token_role_ids(page, slot, card, _CLUB_ROLE_TOKENS)
    price_ids, price_block_ids = _price_node_ids(page, slot, blocks)

    roles = {
        "image": _role_evidence(document, page, image_ids, card_bounds),
        "name": _role_evidence(document, page, name_ids, card_bounds),
        "priceblock": _role_evidence(document, page, price_ids, card_bounds),
        "unit": _role_evidence(document, page, unit_ids, card_bounds),
        "promotion": _role_evidence(document, page, promotion_ids, card_bounds),
        "club": _role_evidence(document, page, club_ids, card_bounds),
    }

    family_signature = _family_signature(roles)
    encoded_signature = json.dumps(family_signature, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    family_id = "slot-family-" + sha256(encoded_signature.encode("utf-8")).hexdigest()[:12]
    example_id = f"page-{page_index}:slot-{slot.id}"

    association = _image_association(
        document,
        page,
        name_ids,
        image_ids,
        confidence=float(slot.confidence or 0.0),
        source_name=source_name,
        source_sha256=source_sha256,
        page_index=page_index,
        slot_id=slot.id,
    )

    preset_id = str(slot.metadata.get("preset_id") or "")
    return {
        "example_id": example_id,
        "slot_id": slot.id,
        "product_card_id": card_id,
        "source_page": page_index,
        "source_page_id": page.id,
        "source_page_name": page.name,
        "source_node_ids": source_node_ids,
        "confidence": round(max(0.0, min(1.0, float(slot.confidence or 0.0))), 6),
        "preset_id": preset_id,
        "family_id": family_id,
        "family_signature": family_signature,
        "expected_product_center": {
            "x": card_bounds.center_x,
            "y": card_bounds.center_y,
            "relative_x": 0.5,
            "relative_y": 0.5,
        },
        "expected_card_bounds": _rect_payload(card_bounds, page=page),
        "expected_image_bounds": roles["image"],
        "expected_name_bounds": roles["name"],
        "expected_priceblock_bounds": roles["priceblock"],
        "expected_unit_bounds": roles["unit"],
        "expected_promotion_bounds": roles["promotion"],
        "expected_club_bounds": roles["club"],
        "price_block_ids": price_block_ids,
        "product_image_association": association,
    }


def _source_node_ids(page: GraphicsPage, slot: SmartSlot, card: dict[str, Any] | None) -> list[str]:
    ids: list[str] = []
    _extend_unique(ids, slot.node_by_role.values(), page)
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for value in extras.values():
            raw = value if isinstance(value, (list, tuple, set)) else [value]
            _extend_unique(ids, raw, page)
    if card:
        _extend_unique(ids, card.get("members") or [], page)
        metadata = card.get("metadata")
        if isinstance(metadata, dict):
            _extend_unique(ids, metadata.get("content_members") or [], page)
            group_id = str(metadata.get("source_group_id") or "")
            if group_id and group_id in page.nodes:
                _extend_unique(ids, [group_id, *page.descendants(group_id)], page)
    return ids


def _card_bounds(
    page: GraphicsPage,
    slot: SmartSlot,
    card: dict[str, Any] | None,
    source_node_ids: list[str],
) -> Rect | None:
    if card and isinstance(card.get("bounds"), dict):
        rect = _rect(card["bounds"])
        if rect.width > 0 and rect.height > 0:
            return rect
    root_id = str(slot.metadata.get("root_node_id") or "")
    if root_id and root_id in page.nodes:
        return page.nodes[root_id].rect.normalized()
    return _bounds_for_nodes(page, source_node_ids)


def _binding_ids(
    page: GraphicsPage,
    slot: SmartSlot,
    card: dict[str, Any] | None,
    aliases: Iterable[str],
) -> list[str]:
    wanted = {str(alias).casefold() for alias in aliases}
    ids: list[str] = []
    for role, node_id in slot.node_by_role.items():
        if str(role).casefold() in wanted:
            _extend_unique(ids, [node_id], page)
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for role, value in extras.items():
            if str(role).casefold() not in wanted:
                continue
            raw = value if isinstance(value, (list, tuple, set)) else [value]
            _extend_unique(ids, raw, page)
    if card and isinstance(card.get("roles"), dict):
        for role, raw in card["roles"].items():
            if str(role).casefold() in wanted:
                _extend_unique(ids, raw if isinstance(raw, list) else [raw], page)
    return ids


def _token_role_ids(
    page: GraphicsPage,
    slot: SmartSlot,
    card: dict[str, Any] | None,
    tokens: tuple[str, ...],
) -> list[str]:
    ids: list[str] = []
    sources: list[dict[str, Any]] = []
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        sources.append(extras)
    if card and isinstance(card.get("roles"), dict):
        sources.append(card["roles"])
    for source in sources:
        for role, value in source.items():
            key = str(role).casefold()
            if not any(token in key for token in tokens):
                continue
            raw = value if isinstance(value, (list, tuple, set)) else [value]
            _extend_unique(ids, raw, page)
    return ids


def _price_node_ids(
    page: GraphicsPage,
    slot: SmartSlot,
    blocks: dict[str, Any],
) -> tuple[list[str], list[str]]:
    block_ids = [str(item) for item in slot.metadata.get("semantic_price_block_ids") or [] if item]
    ids: list[str] = []
    for block_id in block_ids:
        block = blocks.get(block_id)
        if not isinstance(block, dict):
            continue
        _extend_unique(ids, block.get("members") or [], page)
    if not ids:
        for role in _PRICE_BINDINGS:
            node_id = slot.node_by_role.get(role)
            if node_id:
                _extend_unique(ids, [node_id], page)
    return ids, block_ids


def _role_evidence(
    document: GraphicsDocument,
    page: GraphicsPage,
    node_ids: list[str],
    card_bounds: Rect,
) -> dict[str, Any] | None:
    bounds = _bounds_for_nodes(page, node_ids)
    if bounds is None:
        return None
    nodes = [page.nodes[node_id] for node_id in node_ids if node_id in page.nodes]
    payload: dict[str, Any] = {
        "node_ids": [node.id for node in nodes],
        "bounds": _rect_payload(bounds),
        "relative_bounds": _relative_payload(bounds, card_bounds),
        "center": {"x": bounds.center_x, "y": bounds.center_y},
    }
    texts = [" ".join(node.text.replace("\n", " ").split()) for node in nodes if node.text.strip()]
    if texts:
        payload["texts"] = texts
    assets = []
    for node in nodes:
        if not node.asset_id:
            continue
        asset = document.assets.get(node.asset_id)
        assets.append(
            {
                "node_id": node.id,
                "asset_id": node.asset_id,
                "source": asset.source if asset is not None else "",
                "sha256": asset.sha256 if asset is not None else "",
                "fit": str(node.style.get("fit") or ""),
                "crop": dict(node.style.get("crop") or {}) if isinstance(node.style.get("crop"), dict) else {},
            }
        )
    if assets:
        payload["assets"] = assets
    return payload


def _image_association(
    document: GraphicsDocument,
    page: GraphicsPage,
    name_ids: list[str],
    image_ids: list[str],
    *,
    confidence: float,
    source_name: str,
    source_sha256: str,
    page_index: int,
    slot_id: str,
) -> dict[str, Any] | None:
    name_node = next((page.nodes[node_id] for node_id in name_ids if node_id in page.nodes and page.nodes[node_id].text.strip()), None)
    image_node = next((page.nodes[node_id] for node_id in image_ids if node_id in page.nodes and page.nodes[node_id].asset_id), None)
    if name_node is None or image_node is None:
        return None
    product_name = " ".join(name_node.text.replace("\n", " ").split()).strip()
    normalized = normalize_product_name(product_name)
    if not normalized:
        return None
    asset = document.assets.get(image_node.asset_id)
    return {
        "product_name": product_name,
        "normalized_name": normalized,
        "image_node_id": image_node.id,
        "asset_id": image_node.asset_id,
        "image_sha256": asset.sha256 if asset is not None else "",
        "image_source": asset.source if asset is not None else "",
        "confidence": round(max(0.0, min(1.0, confidence)), 6),
        "provenance": {
            "source_file": source_name,
            "source_sha256": source_sha256,
            "source_page": page_index,
            "source_page_id": page.id,
            "slot_id": slot_id,
            "name_node_id": name_node.id,
            "image_node_id": image_node.id,
        },
    }


def _family_signature(roles: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    def quantized(role: str) -> list[float] | None:
        evidence = roles.get(role)
        if not evidence:
            return None
        relative = evidence.get("relative_bounds")
        if not isinstance(relative, dict):
            return None
        return [
            _quantize(float(relative.get(key) or 0.0))
            for key in ("x", "y", "width", "height")
        ]

    return {
        "image": quantized("image"),
        "name": quantized("name"),
        "priceblock": quantized("priceblock"),
        "unit": quantized("unit"),
        "has_promotion": bool(roles.get("promotion")),
        "has_club": bool(roles.get("club")),
    }


def _quantize(value: float, step: float = 0.05) -> float:
    return round(round(value / step) * step, 4)


def _bounds_for_nodes(page: GraphicsPage, node_ids: Iterable[str]) -> Rect | None:
    result: Rect | None = None
    for node_id in node_ids:
        node = page.node(str(node_id))
        if node is None:
            continue
        rect = node.rect.normalized()
        if rect.width <= 0 or rect.height <= 0:
            continue
        result = rect if result is None else result.union(rect)
    return result


def _rect(raw: dict[str, Any]) -> Rect:
    return Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        max(0.0, float(raw.get("width") or 0.0)),
        max(0.0, float(raw.get("height") or 0.0)),
    ).normalized()


def _rect_payload(rect: Rect, *, page: GraphicsPage | None = None) -> dict[str, float]:
    payload = {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}
    if page is not None:
        payload.update(
            {
                "relative_page_x": rect.x / max(page.width, 1e-9),
                "relative_page_y": rect.y / max(page.height, 1e-9),
                "relative_page_width": rect.width / max(page.width, 1e-9),
                "relative_page_height": rect.height / max(page.height, 1e-9),
            }
        )
    return payload


def _relative_payload(child: Rect, parent: Rect) -> dict[str, float]:
    return {
        "x": (child.x - parent.x) / max(parent.width, 1e-9),
        "y": (child.y - parent.y) / max(parent.height, 1e-9),
        "width": child.width / max(parent.width, 1e-9),
        "height": child.height / max(parent.height, 1e-9),
    }


def _extend_unique(target: list[str], values: Iterable[Any], page: GraphicsPage) -> None:
    for value in values:
        node_id = str(value or "")
        if node_id and node_id in page.nodes and node_id not in target:
            target.append(node_id)
