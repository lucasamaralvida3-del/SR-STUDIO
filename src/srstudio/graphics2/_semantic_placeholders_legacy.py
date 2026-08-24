from __future__ import annotations

"""Recuperação segura de ProductCards/área de imagem em placeholders Canva.

Alguns PPTX exportados pelo Canva possuem o card branco e o preço, mas nenhuma
foto dentro do arquivo. Em outros, nome, preço e backplate não pertencem ao
mesmo grupo DrawingML. Esta camada usa o placeholder branco como uma segunda
âncora espacial forte: promove PriceBlocks órfãos a ProductCards e cria somente
uma área de imagem sintética, mantendo o artwork original intacto.
"""

from dataclasses import asdict, dataclass, field
from typing import Any
import re

from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, SmartSlot, Transform
from .semantic_blocks import semantic_block

_PLACEHOLDER_FILLS = {"#FFFFFF", "#FFF", "WHITE", "THEME:LT1", "THEME:BG1"}
_ALPHA_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_GLOBAL_COPY_RE = re.compile(
    r"\b(?:OFERTAS?\s+V[ÁA]LIDAS?|V[ÁA]LIDAS?\s+SOMENTE|SOMENTE\s+DIA|SANTA\s+JULIANA)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class PlaceholderRecoveryReport:
    pages_scanned: int = 0
    slots_scanned: int = 0
    orphan_price_blocks: int = 0
    orphan_cards_promoted: int = 0
    placeholders_matched: int = 0
    synthetic_image_slots: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def recover_canva_image_placeholders(document: GraphicsDocument) -> PlaceholderRecoveryReport:
    """Promove PriceBlocks órfãos e preenche bindings IMAGE ausentes.

    Ordem de recuperação:
    1. PriceBlock sem Smart Slot + placeholder branco + nome local => ProductCard;
    2. qualquer Smart Slot sem IMAGE => área de imagem sintética no placeholder.

    O node sintético é determinístico e invisível até um produto com imagem ser
    aplicado. Reexecutar a função não duplica nodes nem desloca o template.
    """

    report = PlaceholderRecoveryReport()
    for page in document.pages:
        report.pages_scanned += 1
        used_placeholders: set[str] = set()
        used_names: set[str] = set()

        # Primeiro reserve backplates/nome dos slots já reconhecidos para que o
        # fallback não roube contexto de um card que já possui identidade.
        for slot in page.slots.values():
            name_id = str(slot.node_by_role.get(BindingRole.NAME.value) or "")
            if name_id:
                used_names.add(name_id)
            placeholder_id = str(slot.metadata.get("recovered_image_placeholder_id") or "")
            if placeholder_id:
                used_placeholders.add(placeholder_id)

        _promote_orphan_price_blocks(page, used_placeholders, used_names, report)

        # list(...) é intencional: a fase anterior pode ter criado Smart Slots.
        for slot in list(page.slots.values()):
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


def _promote_orphan_price_blocks(
    page: GraphicsPage,
    used_placeholders: set[str],
    used_names: set[str],
    report: PlaceholderRecoveryReport,
) -> None:
    blocks = page.metadata.get("semantic_blocks")
    if not isinstance(blocks, dict):
        return
    orphan_blocks = [
        block
        for block in blocks.values()
        if isinstance(block, dict)
        and str(block.get("kind") or "") == "price_block"
        and not str(block.get("slot_id") or "")
        and bool(dict(block.get("metadata") or {}).get("recovered"))
    ]
    report.orphan_price_blocks += len(orphan_blocks)
    for block in orphan_blocks:
        raw_bounds = block.get("bounds")
        if not isinstance(raw_bounds, dict):
            continue
        price_rect = _rect(raw_bounds)
        if price_rect.width <= 0 or price_rect.height <= 0:
            continue
        placeholder = _find_placeholder(page, price_rect, used_placeholders)
        if placeholder is None:
            continue
        name_node = _find_name_for_placeholder(page, placeholder, price_rect, used_names)
        if name_node is None:
            continue
        slot = _make_placeholder_product_slot(page, block, name_node, placeholder)
        if slot is None:
            continue
        used_placeholders.add(placeholder.id)
        used_names.add(name_node.id)
        report.orphan_cards_promoted += 1


def _make_placeholder_product_slot(
    page: GraphicsPage,
    price_block: dict[str, Any],
    name_node: GraphicsNode,
    placeholder: GraphicsNode,
) -> SmartSlot | None:
    price_id = str(price_block.get("id") or "")
    if not price_id:
        return None
    roles = price_block.get("roles")
    if not isinstance(roles, dict):
        return None
    node_by_role: dict[str, str] = {}
    role_map = {
        "currency": BindingRole.CURRENCY.value,
        "reais": BindingRole.PRICE_REAIS.value,
        "cents": BindingRole.PRICE_CENTS.value,
        "unit": BindingRole.UNIT.value,
        "complete": BindingRole.RETAIL_PRICE.value,
    }
    for canonical, binding in role_map.items():
        raw_ids = roles.get(canonical)
        if isinstance(raw_ids, list) and raw_ids:
            node_id = str(raw_ids[0])
            if node_id in page.nodes:
                node_by_role[binding] = node_id
    if not node_by_role:
        return None
    node_by_role[BindingRole.NAME.value] = name_node.id

    stable = str(price_id).removeprefix("priceblock:recovered:") or _safe_key(price_id)
    card_id = f"productcard:recovered:placeholder:{stable}"
    slot_id = f"slot:recovered:placeholder-{stable}"
    if slot_id in page.slots:
        return page.slots[slot_id]

    _mark_editable(name_node)
    price_members = [
        node_id
        for raw_ids in roles.values()
        if isinstance(raw_ids, list)
        for node_id in (str(item) for item in raw_ids)
        if node_id in page.nodes
    ]
    content = list(dict.fromkeys([*price_members, name_node.id]))
    for node_id in content:
        page.nodes[node_id].metadata["semantic_product_card_id"] = card_id
    placeholder.metadata["semantic_product_card_visual_id"] = card_id

    combined = _bounds_for_nodes(page, content)
    visual_bounds = combined.union(placeholder.rect.normalized()) if combined is not None else placeholder.rect.normalized()
    card = {
        "id": card_id,
        "kind": "product_card",
        "slot_id": slot_id,
        "members": content,
        "roles": {BindingRole.NAME.value: [name_node.id]},
        "bounds": _rect_dict(visual_bounds),
        "template_geometry": {
            node_id: _geometry(page.nodes[node_id], visual_bounds)
            for node_id in content
        },
        "metadata": {
            "price_blocks": [price_id],
            "content_members": content,
            "source_group_id": "",
            "stable_key": f"placeholder-{stable}",
            "confidence": 0.95,
            "atomic": True,
            "editable": True,
            "recovered": True,
            "placeholder_anchored": True,
            "image_placeholder_node_id": placeholder.id,
            "preserve_source_geometry": True,
            "source": "placeholder-card-recovery",
        },
    }
    blocks = page.metadata.get("semantic_blocks")
    if isinstance(blocks, dict):
        blocks[card_id] = card
        # O PriceBlock passa a apontar para o Smart Slot recém-criado.
        price_block["slot_id"] = slot_id
        price_meta = price_block.setdefault("metadata", {})
        if isinstance(price_meta, dict):
            price_meta["smart_slot_id"] = slot_id

    slot = SmartSlot(
        id=slot_id,
        name=_clean_text(name_node.text),
        page_id=page.id,
        node_by_role=node_by_role,
        confidence=0.95,
        metadata={
            "source": "canva-smart-slot",
            "semantic_recovered": True,
            "recovered_from_pptx_group": False,
            "recovered_spatial": True,
            "recovered_from_placeholder": True,
            "semantic_product_card_id": card_id,
            "semantic_price_block_ids": [price_id],
            "recovered_image_placeholder_id": placeholder.id,
            "product_snapshot": {},
        },
    )
    page.slots[slot.id] = slot
    return slot


def _find_name_for_placeholder(
    page: GraphicsPage,
    placeholder: GraphicsNode,
    price: Rect,
    used_names: set[str],
) -> GraphicsNode | None:
    pr = placeholder.rect.normalized()
    candidates: list[tuple[float, GraphicsNode]] = []
    max_above = max(page.height * 0.095, pr.height * 0.75)
    max_below = max(page.height * 0.020, pr.height * 0.20)
    for node in page.nodes.values():
        if node.id in used_names or node.kind is not NodeKind.TEXT or not node.visible:
            continue
        if node.metadata.get("semantic_price_block_id"):
            continue
        text = _clean_text(node.text)
        if not _is_name_text(text):
            continue
        nr = node.rect.normalized()
        # Nome costuma terminar imediatamente antes do quadro branco; aceita-se
        # pequena sobreposição porque fontes Canva podem ultrapassar a bbox.
        vertical_gap = pr.y - nr.bottom
        if vertical_gap > max_above or vertical_gap < -max_below:
            continue
        overlap = _axis_overlap(nr.x, nr.right, pr.x, pr.right)
        center_dx = abs(nr.center_x - pr.center_x) / max(page.width, 1.0)
        if overlap <= 0 and center_dx > 0.13:
            continue
        overlap_ratio = overlap / max(min(nr.width, pr.width), 1.0) if overlap > 0 else 0.0
        price_dx = abs(nr.center_x - price.center_x) / max(page.width, 1.0)
        score = abs(vertical_gap) / max(page.height, 1.0) + center_dx * 1.6 + price_dx * 0.35 - overlap_ratio * 0.35
        candidates.append((score, node))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -float(item[1].style.get("font_size") or 0.0), item[1].id))
    return candidates[0][1]


def _is_name_text(text: str) -> bool:
    if len(text) < 3 or len(text) > 120 or not _ALPHA_RE.search(text):
        return False
    if _DATE_RE.search(text) or _GLOBAL_COPY_RE.search(text):
        return False
    normalized = text.upper().strip()
    if normalized in {"R$", "KG", "/KG", "UN", "/UN", "G", "L", "ML", "LT"}:
        return False
    return True


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
    block["bounds"] = _rect_dict(combined)
    synthetic.metadata["semantic_product_card_id"] = card_id
    placeholder.metadata.setdefault("semantic_product_card_visual_id", card_id)


def _mark_editable(node: GraphicsNode) -> None:
    if "semantic_source_locked" not in node.metadata:
        node.metadata["semantic_source_locked"] = bool(node.locked)
    node.metadata["semantic_recovered_editable"] = True
    node.locked = False


def _bounds_for_nodes(page: GraphicsPage, node_ids: list[str]) -> Rect | None:
    rect: Rect | None = None
    for node_id in node_ids:
        node = page.node(node_id)
        if node is None:
            continue
        rect = node.rect.normalized() if rect is None else rect.union(node.rect.normalized())
    return rect


def _geometry(node: GraphicsNode, bounds: Rect) -> dict[str, float]:
    width = max(bounds.width, 1e-9)
    height = max(bounds.height, 1e-9)
    return {
        "x": node.transform.x,
        "y": node.transform.y,
        "width": node.transform.width,
        "height": node.transform.height,
        "rotation": node.transform.rotation,
        "relative_x": (node.transform.x - bounds.x) / width,
        "relative_y": (node.transform.y - bounds.y) / height,
        "relative_width": node.transform.width / width,
        "relative_height": node.transform.height / height,
    }


def _rect(raw: dict[str, Any]) -> Rect:
    return Rect(
        float(raw.get("x") or 0.0),
        float(raw.get("y") or 0.0),
        max(0.0, float(raw.get("width") or 0.0)),
        max(0.0, float(raw.get("height") or 0.0)),
    )


def _rect_dict(rect: Rect) -> dict[str, float]:
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _axis_overlap(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))


def _safe_key(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "slot")).strip("-").lower()
    return text or "slot"
