from __future__ import annotations

"""Recuperação segura de área de imagem para ProductCards Canva.

Alguns PPTX exportados pelo Canva possuem o card branco e o preço, mas nenhuma
foto dentro do arquivo. Nesses casos não existe node IMAGE para o Smart Slot.
Esta camada detecta o placeholder branco perto do PriceBlock e cria somente uma
área de imagem sintética, mantendo o artwork original intacto.
"""

from dataclasses import asdict, dataclass, field
from typing import Any
import re

from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, Transform
from .semantic_blocks import semantic_block

_PLACEHOLDER_FILLS = {"#FFFFFF", "#FFF", "WHITE", "THEME:LT1", "THEME:BG1"}


@dataclass(slots=True)
class PlaceholderRecoveryReport:
    pages_scanned: int = 0
    slots_scanned: int = 0
    placeholders_matched: int = 0
    synthetic_image_slots: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def recover_canva_image_placeholders(document: GraphicsDocument) -> PlaceholderRecoveryReport:
    """Preenche bindings IMAGE ausentes sem apagar ou converter o backplate.

    O node sintético é determinístico e invisível até um produto com imagem ser
    aplicado. Reexecutar a função não duplica nodes.
    """

    report = PlaceholderRecoveryReport()
    for page in document.pages:
        report.pages_scanned += 1
        used_placeholders: set[str] = set()
        for slot in page.slots.values():
            report.slots_scanned += 1
            if slot.node_by_role.get(BindingRole.IMAGE.value):
                continue
            price_rect = _price_rect(page, slot)
            if price_rect is None:
                continue
            placeholder = _find_placeholder(page, price_rect, used_placeholders)
            if placeholder is None:
                continue
            image_rect = _image_box(page, placeholder.rect.normalized(), price_rect)
            if image_rect is None:
                continue
            used_placeholders.add(placeholder.id)
            report.placeholders_matched += 1
            synthetic = _ensure_synthetic_image_node(page, slot.id, placeholder, image_rect, price_rect)
            slot.node_by_role[BindingRole.IMAGE.value] = synthetic.id
            slot.metadata["recovered_image_placeholder_id"] = placeholder.id
            slot.metadata["synthetic_image_node_id"] = synthetic.id
            slot.metadata["synthetic_image_slot"] = True
            _attach_to_semantic_card(page, slot, placeholder, synthetic)
            report.synthetic_image_slots += 1
    document.metadata["semantic_image_placeholders"] = report.to_dict()
    return report


def _price_rect(page: GraphicsPage, slot) -> Rect | None:
    price_block_ids = [str(item) for item in slot.metadata.get("semantic_price_block_ids") or [] if item]
    for block_id in price_block_ids:
        block = semantic_block(page, block_id)
        if block and isinstance(block.get("bounds"), dict):
            return _rect(block["bounds"])
    ids = [
        slot.node_by_role.get(BindingRole.CURRENCY.value, ""),
        slot.node_by_role.get(BindingRole.PRICE_REAIS.value, ""),
        slot.node_by_role.get(BindingRole.PRICE_CENTS.value, ""),
        slot.node_by_role.get(BindingRole.UNIT.value, ""),
        slot.node_by_role.get(BindingRole.RETAIL_PRICE.value, ""),
    ]
    return page.bounds([node_id for node_id in ids if node_id])


def _find_placeholder(page: GraphicsPage, price: Rect, used: set[str]) -> GraphicsNode | None:
    page_area = max(page.width * page.height, 1.0)
    pcx, pcy = price.center_x, price.center_y
    best: tuple[float, GraphicsNode] | None = None
    for node in page.nodes.values():
        if node.id in used or node.kind not in {NodeKind.RECT, NodeKind.PATH}:
            continue
        if node.metadata.get("semantic_synthetic_image_slot"):
            continue
        fill = str(node.style.get("fill") or "").strip().upper()
        if fill not in _PLACEHOLDER_FILLS:
            continue
        rect = node.rect.normalized()
        if rect.width <= 0 or rect.height <= 0:
            continue
        wr = rect.width / max(page.width, 1.0)
        hr = rect.height / max(page.height, 1.0)
        area = rect.width * rect.height / page_area
        if not (0.010 <= area <= 0.075 and 0.10 <= wr <= 0.34 and 0.075 <= hr <= 0.26):
            continue
        dx = abs(rect.center_x - pcx) / max(page.width, 1.0)
        dy = abs(rect.center_y - pcy) / max(page.height, 1.0)
        if dx > 0.20 or dy > 0.23:
            continue
        price_inside_y = rect.y - page.height * 0.025 <= pcy <= rect.bottom + page.height * 0.045
        if not price_inside_y:
            continue
        overlap = _axis_overlap(price.x, price.right, rect.x, rect.right)
        if overlap <= 0:
            continue
        # Preferimos o backplate mais próximo e que contém maior parte do preço
        # horizontalmente. O leve bônus para placeholder acima do preço segue o
        # padrão real dos cards SR/Canva.
        overlap_ratio = overlap / max(min(price.width, rect.width), 1.0)
        score = dx * 1.8 + dy - overlap_ratio * 0.25 + (0.0 if rect.y <= pcy else 0.18)
        if best is None or score < best[0]:
            best = (score, node)
    return best[1] if best is not None else None


def _image_box(page: GraphicsPage, placeholder: Rect, price: Rect) -> Rect | None:
    inset_x = max(2.0, placeholder.width * 0.055)
    inset_top = max(2.0, placeholder.height * 0.045)
    left = placeholder.x + inset_x
    right = placeholder.right - inset_x
    top = placeholder.y + inset_top
    fallback_bottom = placeholder.y + placeholder.height * 0.58
    bottom = fallback_bottom
    gap = max(2.0, page.height * 0.006)
    if placeholder.y < price.y < placeholder.bottom:
        bottom = min(bottom, price.y - gap)
    min_height = max(8.0, page.height * 0.026)
    if bottom - top < min_height:
        bottom = min(placeholder.bottom - max(2.0, placeholder.height * 0.08), top + min_height)
    if right <= left or bottom <= top:
        return None
    return Rect(left, top, right - left, bottom - top)


def _ensure_synthetic_image_node(
    page: GraphicsPage,
    slot_id: str,
    placeholder: GraphicsNode,
    image_rect: Rect,
    price_rect: Rect,
) -> GraphicsNode:
    stable = _safe_key(slot_id)
    node_id = f"node:semantic-image:{stable}"
    existing = page.node(node_id)
    if existing is not None:
        existing.transform = Transform(
            x=image_rect.x,
            y=image_rect.y,
            width=image_rect.width,
            height=image_rect.height,
        )
        return existing
    price_z = min(
        (
            node.z_index
            for node in page.nodes.values()
            if node.rect.normalized().x <= price_rect.right
            and node.rect.normalized().right >= price_rect.x
            and node.rect.normalized().y <= price_rect.bottom
            and node.rect.normalized().bottom >= price_rect.y
        ),
        default=placeholder.z_index + 2,
    )
    z_index = max(placeholder.z_index + 1, price_z - 1)
    node = GraphicsNode(
        id=node_id,
        kind=NodeKind.IMAGE,
        name="SR Smart Image Slot",
        transform=Transform(
            x=image_rect.x,
            y=image_rect.y,
            width=image_rect.width,
            height=image_rect.height,
        ),
        z_index=z_index,
        locked=False,
        visible=False,
        opacity=1.0,
        style={
            "fit": "contain",
            "crop": {},
            "fill_rect": {},
            "zoom": 1.0,
            "focus_x": 0.5,
            "focus_y": 0.5,
        },
        metadata={
            "source": "semantic-placeholder-recovery",
            "semantic_synthetic_image_slot": True,
            "placeholder_node_id": placeholder.id,
            "slot_id": slot_id,
            "slot_role": BindingRole.IMAGE.value,
            "template_hidden": True,
        },
    )
    page.add_node(node)
    return node


def _attach_to_semantic_card(page: GraphicsPage, slot, placeholder: GraphicsNode, synthetic: GraphicsNode) -> None:
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    block = semantic_block(page, card_id) if card_id else None
    if not block:
        return
    roles = block.setdefault("roles", {})
    roles[BindingRole.IMAGE.value] = [synthetic.id]
    members = block.setdefault("members", [])
    if synthetic.id not in members:
        members.append(synthetic.id)
    metadata = block.setdefault("metadata", {})
    content = metadata.setdefault("content_members", [])
    for node_id in (placeholder.id, synthetic.id):
        if node_id not in content:
            content.append(node_id)
    metadata["image_placeholder_node_id"] = placeholder.id
    metadata["synthetic_image_node_id"] = synthetic.id
    metadata["drop_bounds_from_placeholder"] = True
    old_bounds = _rect(block.get("bounds") or {})
    combined = old_bounds.union(placeholder.rect.normalized()) if old_bounds.width > 0 and old_bounds.height > 0 else placeholder.rect.normalized()
    block["bounds"] = {
        "x": combined.x,
        "y": combined.y,
        "width": combined.width,
        "height": combined.height,
    }
    synthetic.metadata["semantic_product_card_id"] = card_id
    placeholder.metadata.setdefault("semantic_product_card_visual_id", card_id)


def _rect(raw: dict[str, Any]) -> Rect:
    return Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        max(0.0, float(raw.get("width") or 0.0)),
        max(0.0, float(raw.get("height") or 0.0)),
    )


def _axis_overlap(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))


def _safe_key(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "slot")).strip("-").lower()
    return text or "slot"
