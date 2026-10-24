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
    width = min(page.width * .94, 1180.0)
    # PPT: approximately 4:1 complete strip aspect ratio, not a tall card.
    height = min(page.height * .31, 315.0, width / 4.0)
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
        # PPT: white paper and one round-ended source-blue price ribbon.
        paper = GraphicsNode(
            kind=NodeKind.RECT,
            name="Fundo branco da faixa",
            transform=Transform(x=left, y=top, width=width, height=height * .80),
            z_index=-110,
            style={"fill": "#FFFFFF", "stroke_width": 0},
            metadata={"multi_item_decoration": True, "source_reference": "multi slots(1).pptx"},
        )
        page.add_node(paper, parent_id=root.id)
        footer = GraphicsNode(
            kind=NodeKind.RECT,
            name="Faixa azul contínua",
            transform=Transform(x=left, y=top + height * .77,
                                width=width, height=height * .23),
            z_index=-100,
            style={"fill": "#105594", "stroke_width": 0, "radius_ratio": .29},
            metadata={"multi_item_decoration": True},
        )
        page.add_node(footer, parent_id=root.id)

    # Five equal columns in source. A single uninterrupted price ribbon.
    gap = 0.0
    cell_width = width / count
    child_ids: list[str] = []
    with session.transaction("Adicionar separadores do Multi Itens"):
        for index in range(1, count):
            separator = GraphicsNode(
                kind=NodeKind.RECT,
                name=f"Divisor {index}",
                transform=Transform(x=left + index * cell_width - 1.2,
                                    y=top + height * .17, width=2.4,
                                    height=height * .56),
                z_index=8,
                style={"fill": "#105594", "stroke_width": 0},
                metadata={"multi_item_decoration": True},
            )
            page.add_node(separator, parent_id=root.id)
    for index in range(count):
        cell_x = left + index * cell_width
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
        root.metadata["reference_pptx"] = "multi slots(1).pptx"
        root.metadata["reference_fidelity_revision"] = 45
    session.selection = {root.id}
    session.anchor_id = root.id
    return {"root_node_id": root.id, "slot_ids": child_ids,
            "count": count, "price_mode": price_mode}
