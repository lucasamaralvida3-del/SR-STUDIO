from __future__ import annotations

"""Composition is a placement map over ORIGINAL canonical Smart Slot artwork.

Reference-led layouts prefer Slot Único. A Multi 2–8 ribbon is a single
parent group with individually editable product cells, not a grid of fake
cards. Never silently discard a filled product, break a saved Multi or
change the style of an existing filled slot.
"""

from dataclasses import dataclass

from .item_slots import create_item_slot, is_manual_item_slot, set_reference_price_mode
from .multi_item_strip import create_multi_item_strip, set_multi_item_count
from .promotion_layouts import PromotionPlan
from .campaign_tools import apply_default_slot_theme


@dataclass(frozen=True)
class CompositionResult:
    slot_ids: tuple[str, ...]
    reused_slot_ids: tuple[str, ...]
    created_slot_ids: tuple[str, ...]
    root_node_ids: tuple[str, ...]
    unused_slot_ids: tuple[str, ...]


def _fit_component(x: float, y: float, w: float, h: float, ratio: float):
    """Preserve PPTX proportions by fitting entire slot groups, not stretching art."""
    if min(w, h, ratio) <= 0:
        raise ValueError("Área inválida para composição de Smart Slots.")
    if w / h > ratio:
        fw, fh = h * ratio, h
    else:
        fw, fh = w, w / ratio
    return (x + (w - fw) / 2, y + (h - fh) / 2, fw, fh)


def _valid_multi_groups(page):
    out = []
    for node in page.nodes.values():
        if not node.metadata.get("multi_slot_beta44"):
            continue
        ids = list(node.metadata.get("child_slot_ids") or [])
        if ids and all(sid in page.slots for sid in ids):
            out.append((node, ids))
    return out


def apply_slot_composition(session, plan: PromotionPlan, *, price_mode: str = "auto",
                           reuse_existing: bool = True) -> CompositionResult:
    if price_mode not in ("auto", "one", "two"):
        raise ValueError("Modo de preços inválido.")
    page = session.page
    original = dict(page.slots)
    positions = list(plan.placements)
    populated = [slot for slot in original.values() if slot.product_id]
    capacity = len(positions)
    if reuse_existing and len(populated) > capacity:
        raise ValueError(
            f"Layout comporta {capacity} produtos, mas a página possui "
            f"{len(populated)} Smart Slots preenchidos. "
            "Escolha um layout maior antes de reorganizar."
        )

    multi_places = [p for p in positions if p.kind == "multi"]
    multi_count = len(multi_places)
    multi_start = multi_places[0].index if multi_places else -1
    upper_count = capacity - multi_count

    # Reuse canonical Individual or Único slots; never treat one Multi cell
    # as an independent individual card.
    singles = [
        s for s in original.values()
        if is_manual_item_slot(s) and not s.metadata.get("multi_parent_id")
        and (s.metadata.get("preset_id") == "individual-beta44" or
             s.metadata.get("limpeza_blue_profile") == "limpeza-blue-v1")
        and page.node(str(s.metadata.get("root_node_id") or "")) is not None
    ] if reuse_existing else []
    singles.sort(key=lambda s: not bool(s.product_id))

    roots = _valid_multi_groups(page) if reuse_existing else []
    filled_multi = [
        (root, ids) for root, ids in roots
        if any(page.slots[sid].product_id for sid in ids)
    ]

    # The auto layout may center an existing complete Multi as ONE component.
    if (plan.mode == "auto" and not singles and len(roots) == 1
            and len(roots[0][1]) == capacity and 2 <= capacity <= 8):
        root, ids = roots[0]
        width = page.width * .91
        top = page.height * (plan.logo_reserved + .025)
        available = page.height * .975 - top
        height = min(width / 4.75, available)
        session.resize_node(root.id, x=page.width * .045,
                            y=top + (available - height) / 2,
                            width=width, height=height)
        set_reference_price_mode(session, ids, price_mode)
        with session.transaction("Auto Layout com faixa Multi existente"):
            page.metadata["promotion_composition"] = {
                "mode": plan.mode, "logo_reserved": plan.logo_reserved,
                "slot_ids": ids, "root_node_ids": [root.id],
                "component_source": "canonical-smart-slots",
                "multi_count": capacity,
            }
        return CompositionResult(tuple(ids), tuple(ids), (), (root.id,),
                                 tuple(sid for sid in original if sid not in ids))

    # Preserve existing populated standalone slots. If a legacy scene has
    # 11 populated Individual cards, don't lose 5 products to make a strip.
    preserve_all_singles = (
        multi_count > 0 and len([s for s in singles if s.product_id]) > upper_count
        and not filled_multi
    )
    use_multi = multi_count > 0 and not preserve_all_singles

    selected_multi = None
    if use_multi and roots:
        # Prefer matching size and already populated ribbon, then a safe
        # resize. An old filled fifth cell cannot be lost in a Multi-4 layout.
        compatible = [
            (r, ids) for r, ids in roots
            if len(ids) == multi_count or
            (len(ids) > multi_count and not any(page.slots[sid].product_id
                                               for sid in ids[multi_count:])) or
            (len(ids) < multi_count)
        ]
        if compatible:
            compatible.sort(key=lambda pair:
                (not any(page.slots[sid].product_id for sid in pair[1]),
                 len(pair[1]) != multi_count))
            selected_multi = compatible[0]
    if filled_multi:
        if not use_multi or len(filled_multi) != 1:
            raise ValueError(
                "Esta página possui uma faixa Multi preenchida. "
                "Use um layout compatível; nenhum produto será separado."
            )
        filled_root, filled_ids = filled_multi[0]
        if (selected_multi is None or filled_root.id != selected_multi[0].id or
                any(page.slots[sid].product_id for sid in filled_ids[multi_count:])):
            raise ValueError(
                "Esta página possui uma faixa Multi preenchida. "
                "Não é possível retirar produtos para encaixar outra faixa."
            )

    arranged: list[str] = []
    reused: list[str] = []
    created: list[str] = []
    root_ids: list[str] = []

    def take_single(kind: str, x: float, y: float):
        expected = ("individual-beta44" if kind == "individual"
                    else "limpeza-blue-v1")
        chosen = None
        # A filled slot may keep its original, user-approved visual style.
        for idx, slot in enumerate(singles):
            if (slot.metadata.get("preset_id") == expected or
                    slot.metadata.get("limpeza_blue_profile") == expected):
                chosen = singles.pop(idx)
                break
        if chosen is None:
            for idx, slot in enumerate(singles):
                if slot.product_id:
                    chosen = singles.pop(idx)
                    break
        if chosen is not None:
            reused.append(chosen.id)
            return chosen
        if expected == "limpeza-blue-v1":
            from .slot_limpeza_blue import create_limpeza_blue_slot
            chosen = create_limpeza_blue_slot(session, x=x, y=y)
            apply_default_slot_theme(session, [chosen.id])
        else:
            chosen = create_item_slot(session, "individual-beta44", x=x, y=y)
        created.append(chosen.id)
        return chosen

    for position in positions:
        x = page.width * position.x
        y = page.height * position.y
        w = page.width * position.width
        h = page.height * position.height
        if use_multi and position.kind == "multi":
            if position.index != multi_start:
                continue
            end = multi_places[-1]
            w = page.width * (end.x + end.width - position.x)
            if selected_multi:
                multi_root, ids = selected_multi
                if len(ids) != multi_count:
                    resized = set_multi_item_count(session, multi_root.id, multi_count)
                    old = set(original)
                    ids = resized["slot_ids"]
                    reused.extend(sid for sid in ids if sid in old)
                    created.extend(sid for sid in ids if sid not in old)
                else:
                    reused.extend(ids)
            else:
                result = create_multi_item_strip(
                    session, count=multi_count, price_mode=price_mode, x=x, y=y)
                multi_root = page.node(result["root_node_id"])
                ids = result["slot_ids"]
                created.extend(ids)
            ratio = 4.75  # faithful canonical source; preserve original ribbon
            fx, fy, fw, fh = _fit_component(x, y, w, h, ratio)
            session.resize_node(multi_root.id, x=fx, y=fy, width=fw, height=fh)
            set_reference_price_mode(session, ids, price_mode)
            arranged.extend(ids)
            root_ids.append(multi_root.id)
            continue

        # When all historical singles are filled, retain them rather than
        # dropping product IDs: the grouping must not falsify existing data.
        if position.kind == "multi" and not use_multi:
            target_kind = "single"
        else:
            target_kind = position.kind
        slot = take_single(target_kind, x, y)
        root_id = str(slot.metadata["root_node_id"])
        root = page.node(root_id)
        ratio = (root.rect.width / root.rect.height
                 if root and root.rect.height else 418.0 / 320.0)
        fx, fy, fw, fh = _fit_component(x, y, w, h, ratio)
        session.resize_node(root_id, x=fx, y=fy, width=fw, height=fh)
        if slot.metadata.get("preset_id") == "individual-beta44":
            set_reference_price_mode(session, [slot.id], price_mode)
        arranged.append(slot.id)
        root_ids.append(root_id)

    unused = [sid for sid in original if sid not in arranged]
    with session.transaction("Guardar posicionamento dos Smart Slots reais"):
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
            other = page.node(other_root)
            if other is not None and other_root not in root_ids:
                other.visible = False
        page.metadata["promotion_composition"] = {
            "mode": plan.mode, "logo_reserved": plan.logo_reserved,
            "slot_ids": arranged, "root_node_ids": root_ids,
            "component_source": "canonical-smart-slots",
            "multi_count": multi_count if use_multi else 0,
            "uses_reference_slot_unico": True,
        }
    return CompositionResult(tuple(arranged), tuple(reused),
                             tuple(created), tuple(root_ids), tuple(unused))
