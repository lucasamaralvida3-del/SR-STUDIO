from __future__ import annotations

"""Promotion templates are positioning maps, never separate visual presets.

Every placed element is a canonical editable ItemSlot (individual or the real
Multi-5 parent). Existing product slots are reused before any new blank slot
is created. The layout does not modify product bindings or project assets.
"""

from dataclasses import dataclass

from .item_slots import create_item_slot, is_manual_item_slot, set_reference_price_mode
from .multi_item_strip import create_multi_item_strip
from .promotion_layouts import PromotionPlan
from .model import Rect


@dataclass(frozen=True)
class CompositionResult:
    slot_ids: tuple[str, ...]
    reused_slot_ids: tuple[str, ...]
    created_slot_ids: tuple[str, ...]
    root_node_ids: tuple[str, ...]
    unused_slot_ids: tuple[str, ...]


def _fit_component(x: float, y: float, w: float, h: float, ratio: float):
    """Contain a canonical Smart Slot without distorting its PPTX artwork.

    A composition is a map of *locations*, not permission to stretch its
    original product images, price plate and typography independently.
    """
    if min(w, h, ratio) <= 0:
        raise ValueError("Área inválida para composição de Smart Slots.")
    if w / h > ratio:
        fitted_w, fitted_h = h * ratio, h
    else:
        fitted_w, fitted_h = w, w / ratio
    return (x + (w - fitted_w) / 2, y + (h - fitted_h) / 2,
            fitted_w, fitted_h)


def apply_slot_composition(session, plan: PromotionPlan, *, price_mode: str = "auto",
                           reuse_existing: bool = True) -> CompositionResult:
    """Position real Smart Slots while retaining existing products.

    The 11-product layout uses exactly six independent canonical individual
    slots + a real reusable Multi-5 for the last five items.
    """
    if price_mode not in ("auto", "one", "two"):
        raise ValueError("Modo de preços inválido.")
    page = session.page
    old_slots = dict(page.slots)
    # Never silently leave a filled product behind when the requested
    # composition has fewer positions. Reject BEFORE any move, creation or
    # mutation, preserving the exact page and its undo history.
    populated = [slot for slot in old_slots.values() if slot.product_id]
    capacity = len(plan.placements)
    if reuse_existing and len(populated) > capacity:
        raise ValueError(
            f"Layout comporta {capacity} produtos, mas a página possui "
            f"{len(populated)} Smart Slots preenchidos. "
            "Use um layout com mais posições ou organize os produtos antes."
        )
    # Avoid using a Multi cell as a free-standing single: it belongs to the
    # parent's continuous ribbon, not to an individual price card.
    singles = [
        s for s in old_slots.values()
        if is_manual_item_slot(s)
        and s.metadata.get("preset_id") == "individual-beta44"
        and not s.metadata.get("multi_parent_id")
        and page.node(str(s.metadata.get("root_node_id") or "")) is not None
    ] if reuse_existing else []
    # Certified Azul is also a real Smart Slot, but has its own distinct
    # protected layout. Reuse it only if the user already placed it.
    blue = [
        s for s in old_slots.values()
        if s.metadata.get("limpeza_blue_profile") == "limpeza-blue-v1"
        and page.node(str(s.metadata.get("root_node_id") or "")) is not None
    ] if reuse_existing else []
    singles.extend(blue)
    # Prefer the user's populated product cards, not placeholder cards that
    # happen to have been created earlier. Stable sort preserves manual order
    # among filled products and among empty slots alike.
    singles.sort(key=lambda slot: not bool(slot.product_id))

    # A populated Multi is a SINGLE reusable visual component. We must
    # never separate its children into fake independent cards or leave their
    # products under a new composition. Reject incompatible maps up front.
    filled_multi_roots = {
        str(slot.metadata.get("multi_parent_id"))
        for slot in populated if slot.metadata.get("multi_parent_id")
    }
    if reuse_existing and filled_multi_roots:
        compatible_eleven = (
            plan.mode == "eleven"
            and len(filled_multi_roots) == 1
            and all(
                page.node(root_id) is not None
                and int(page.node(root_id).metadata.get("multi_count") or 0) == 5
                for root_id in filled_multi_roots
            )
        )
        compatible_auto = (
            plan.mode == "auto"
            and len(filled_multi_roots) == 1
            and not singles
            and all(
                page.node(root_id) is not None
                and int(page.node(root_id).metadata.get("multi_count") or 0) == capacity
                for root_id in filled_multi_roots
            )
        )
        if not (compatible_eleven or compatible_auto):
            raise ValueError(
                "Esta página possui uma faixa Multi preenchida. "
                "Use um layout compatível com a faixa existente; os "
                "produtos não serão substituídos nem separados."
            )

    multi5 = None
    if reuse_existing and plan.mode == "eleven":
        for node in page.nodes.values():
            if node.metadata.get("multi_slot_beta44") and int(node.metadata.get("multi_count") or 0) == 5:
                ids = list(node.metadata.get("child_slot_ids") or [])
                if len(ids) == 5 and all(sid in page.slots for sid in ids):
                    multi5 = node
                    break

    # Auto Layout should likewise REPOSITION an existing complete Multi5/
    # Multi6 instead of drawing 5/6 replacement cards over its products.
    if (reuse_existing and plan.mode == "auto" and not singles
            and len(plan.placements) in (5, 6)):
        expected = len(plan.placements)
        for root in page.nodes.values():
            if (root.metadata.get("multi_slot_beta44")
                    and int(root.metadata.get("multi_count") or 0) == expected):
                ids = list(root.metadata.get("child_slot_ids") or [])
                if len(ids) != expected or not all(sid in page.slots for sid in ids):
                    continue
                target_w = page.width * .91
                available_top = page.height * (plan.logo_reserved + .025)
                available_h = page.height * .975 - available_top
                target_h = min(target_w / 4.75, available_h)
                target_x = page.width * .045
                target_y = available_top + max(0, available_h - target_h) / 2
                session.resize_node(root.id, x=target_x, y=target_y,
                                    width=target_w, height=target_h)
                set_reference_price_mode(session, ids, price_mode)
                with session.transaction("Auto Layout com faixa Multi existente"):
                    page.metadata["promotion_composition"] = {
                        "mode": plan.mode,
                        "logo_reserved": plan.logo_reserved,
                        "slot_ids": ids,
                        "root_node_ids": [root.id],
                        "component_source": "canonical-smart-slots",
                    }
                return CompositionResult(tuple(ids), tuple(ids), (), (root.id,),
                                         tuple(sid for sid in old_slots if sid not in ids))

    # If the page already contains eleven actual individual Smart Slots,
    # do not introduce an artificial new Multi strip and abandon five
    # products. In that case the bottom five positions use the existing
    # individual components. A real Multi-5 is preferred if already present.
    use_multi5 = plan.mode == "eleven" and (multi5 is not None or len(singles) <= 6)

    arranged: list[str] = []
    reused: list[str] = []
    created: list[str] = []
    root_ids: list[str] = []
    # Arrange only assigned cards; unrelated elements (logo, text, saved
    # artworks, and unselected extra slots) are never deleted or re-created.
    for position in plan.placements:
        if use_multi5 and position.index in (7, 8, 9, 10):
            continue
        x, y, w, h = (page.width * position.x, page.height * position.y,
                      page.width * position.width, page.height * position.height)
        if use_multi5 and position.index == 6:
            end = plan.placements[10]
            w = page.width * (end.x + end.width - position.x)
            if multi5 is None:
                data = create_multi_item_strip(session, count=5, price_mode=price_mode, x=x, y=y)
                multi_root_id = data["root_node_id"]
                ids = list(data["slot_ids"])
                created.extend(ids)
            else:
                multi_root_id = multi5.id
                ids = list(multi5.metadata.get("child_slot_ids") or [])
                reused.extend(ids)
            fx, fy, fw, fh = _fit_component(x, y, w, h, 4.75)
            session.resize_node(multi_root_id, x=fx, y=fy, width=fw, height=fh)
            set_reference_price_mode(session, ids, price_mode)
            arranged.extend(ids)
            root_ids.append(multi_root_id)
            continue

        if singles:
            slot = singles.pop(0)
            reused.append(slot.id)
        else:
            slot = create_item_slot(session, "individual-beta44", x=x, y=y)
            created.append(slot.id)
        root_id = str(slot.metadata["root_node_id"])
        root = page.node(root_id)
        source_ratio = (root.rect.width / root.rect.height
                        if root and root.rect.height > 0 else 460.0 / 490.0)
        fx, fy, fw, fh = _fit_component(x, y, w, h, source_ratio)
        session.resize_node(root_id, x=fx, y=fy, width=fw, height=fh)
        if slot.metadata.get("preset_id") == "individual-beta44":
            set_reference_price_mode(session, [slot.id], price_mode)
        arranged.append(slot.id)
        root_ids.append(root_id)

    # Hide only unassigned EMPTY manual slots so they cannot overlap the
    # selected composition. Keep their IDs and nodes for subsequent layouts.
    # Unrelated artwork and non-manual imported objects remain untouched.
    unused = [sid for sid in old_slots if sid not in arranged]
    with session.transaction("Guardar posicionamento dos Smart Slots"):
        for root_id in root_ids:
            root = page.node(root_id)
            if root is not None:
                root.visible = True
        for sid in unused:
            slot = page.slots.get(sid)
            if not is_manual_item_slot(slot) or slot.product_id:
                continue
            other_root = str(slot.metadata.get("multi_parent_id") or
                             slot.metadata.get("root_node_id") or "")
            root = page.node(other_root)
            if root is not None and other_root not in root_ids:
                root.visible = False
        page.metadata["promotion_composition"] = {
            "mode": plan.mode,
            "logo_reserved": plan.logo_reserved,
            "slot_ids": list(arranged),
            "root_node_ids": list(root_ids),
            "component_source": "canonical-smart-slots",
        }
    return CompositionResult(tuple(arranged), tuple(reused),
                             tuple(created), tuple(root_ids), tuple(unused))
