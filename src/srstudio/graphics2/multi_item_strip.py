from __future__ import annotations

"""Editable 5/6-product horizontal promotional strips for SR Studio G2."""

from .item_slots import create_item_slot
from .model import GraphicsNode, NodeKind, Transform


def create_multi_item_strip(session, *, count: int = 6, price_mode: str = "auto",
                            x: float | None = None, y: float | None = None) -> dict:
    """One grouped strip, with independent, bindable SmartSlot cells.

    The outer node is a real group, so native group move/resize acts on the
    complete strip. Each cell is also a normal ItemSlot with an independent
    product and optional second price; no product IDs are shared.
    """
    if count not in (5, 6):
        raise ValueError("O Smart Slot Multi Itens aceita 5 ou 6 produtos.")
    if price_mode not in ("auto", "one", "two"):
        raise ValueError("Modo de preços inválido.")
    page = session.page
    width = min(page.width * .92, 1180.0)
    height = min(page.height * .37, 315.0)
    left = (page.width - width) / 2 if x is None else float(x)
    top = page.height * .48 if y is None else float(y)
    root = GraphicsNode(
        kind=NodeKind.GROUP,
        name=f"Smart Slot Multi Itens — {count} produtos",
        transform=Transform(x=left, y=top, width=width, height=height),
        metadata={"multi_slot_beta44": True, "multi_count": count,
                  "price_mode": price_mode, "child_slot_ids": []},
    )
    with session.transaction("Criar faixa Multi Itens"):
        page.add_node(root)
        # The blue strip forms a continuous footer behind all item prices.
        footer = GraphicsNode(
            kind=NodeKind.RECT,
            name="Faixa azul contínua",
            transform=Transform(x=left, y=top + height * .73,
                                width=width, height=height * .27),
            style={"fill": "#265398", "stroke_width": 0},
            metadata={"multi_item_decoration": True},
        )
        page.add_node(footer, parent_id=root.id)

    gap = 2.0
    cell_width = (width - gap * (count - 1)) / count
    child_ids: list[str] = []
    for index in range(count):
        cell_x = left + index * (cell_width + gap)
        slot = create_item_slot(session, "multi-cell-beta44",
                                x=cell_x, y=top)
        child_root_id = str(slot.metadata["root_node_id"])
        with session.transaction("Vincular item à faixa Multi"):
            child_root = page.node(child_root_id)
            old = child_root.rect.normalized()
            from .model import Rect
            session._scale_tree(child_root_id, old,
                                Rect(cell_x, top, cell_width, height))
            page.roots.remove(child_root_id)
            child_root.parent_id = root.id
            root.children.append(child_root_id)
            slot.metadata.update({
                "multi_parent_id": root.id,
                "multi_index": index,
                "multi_count": count,
                "price_mode": price_mode,
            })
            child_ids.append(slot.id)
    with session.transaction("Finalizar Smart Slot Multi"):
        root.metadata["child_slot_ids"] = child_ids
    session.selection = {root.id}
    session.anchor_id = root.id
    return {"root_node_id": root.id, "slot_ids": child_ids,
            "count": count, "price_mode": price_mode}
