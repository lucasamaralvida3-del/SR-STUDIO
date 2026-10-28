from __future__ import annotations

"""Editable 2–8-product horizontal promotional strips for SR Studio G2."""

from .item_slots import create_item_slot
from .model import GraphicsNode, NodeKind, Transform


def create_multi_item_strip(session, *, count: int = 6, price_mode: str = "auto",
                            x: float | None = None, y: float | None = None) -> dict:
    """One grouped strip, with independent, bindable SmartSlot cells.

    The outer node is a real group, so native group move/resize acts on the
    complete strip. Each cell is also a normal ItemSlot with an independent
    product and optional second price; no product IDs are shared.
    """
    if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 8:
        raise ValueError("O Smart Slot Multi Itens aceita de 2 a 8 produtos.")
    if price_mode not in ("auto", "one", "two"):
        raise ValueError("Modo de preços inválido.")
    page = session.page
    width = min(page.width * .94, 1180.0)
    # PPT: approximately 4.75:1 complete strip aspect ratio, not a tall card.
    height = min(page.height * .31, 315.0, width / 4.75)
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
            transform=Transform(x=left, y=top, width=width, height=height * .70),
            z_index=-110,
            style={"fill": "#FFFFFF", "stroke_width": 0},
            metadata={"multi_item_decoration": True, "source_reference": "multi slots(2).pptx"},
        )
        paper.visible = False  # keep compatibility node, never cover campaign artwork
        paper.metadata["transparent_campaign_backplate"] = True
        page.add_node(paper, parent_id=root.id)
        footer = GraphicsNode(
            kind=NodeKind.RECT,
            name="Faixa azul contínua",
            transform=Transform(x=left, y=top + height * .70,
                                width=width, height=height * .30),
            z_index=-100,
            style={"fill": "#105594", "stroke_width": 0, "radius_ratio": .29},
            metadata={"multi_item_decoration": True},
        )
        page.add_node(footer, parent_id=root.id)

    # Any 2–8 equal cells use the SAME canonical Multi cell and common ribbon.
    gap = 0.0
    cell_width = width / count
    child_ids: list[str] = []
    with session.transaction("Adicionar separadores do Multi Itens"):
        for index in range(1, count):
            separator = GraphicsNode(
                kind=NodeKind.RECT,
                name=f"Divisor {index}",
                transform=Transform(x=left + index * cell_width - 1.2,
                                    y=top + height * .14, width=2.4,
                                    height=height * .47),
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
        root.metadata["reference_pptx"] = "multi slots(2).pptx"
        root.metadata["reference_fidelity_revision"] = 47
    from .campaign_tools import THEMES
    theme = str(page.metadata.get("slot_theme") or "azul")
    if theme != "azul":
        target = THEMES.get(theme, theme)
        for nid in page.descendants(root.id):
            n = page.node(nid)
            if n is not None:
                for key in ("fill", "stroke", "color"):
                    val = n.style.get(key)
                    if isinstance(val, str) and val.upper() == "#105594":
                        n.style[key] = target
    session.selection = {root.id}
    session.anchor_id = root.id
    return {"root_node_id": root.id, "slot_ids": child_ids,
            "count": count, "price_mode": price_mode}


def set_multi_item_count(session, root_id: str, count: int) -> dict:
    """Change a real Multi ribbon to 2–8 cells without replacing bound products.

    Keeps all existing cell IDs, product bindings, artwork and original ribbon.
    Shrinking fails *before any mutation* if a discarded cell has a product.
    """
    if isinstance(count, bool) or not isinstance(count, int) or not 2 <= count <= 8:
        raise ValueError("A faixa Multi aceita de 2 a 8 produtos.")
    page = session.page
    root = page.node(str(root_id))
    if root is None or not root.metadata.get("multi_slot_beta44"):
        raise ValueError("Selecione uma faixa Multi real.")
    ids = list(root.metadata.get("child_slot_ids") or [])
    if not ids or any(sid not in page.slots for sid in ids):
        raise ValueError("Os componentes da faixa Multi estão incompletos.")
    if any(page.slots[sid].product_id for sid in ids[count:]):
        raise ValueError(
            "Não é possível diminuir a faixa: existem produtos nos espaços "
            "que seriam removidos. Retire ou reorganize esses produtos primeiro."
        )
    if count == len(ids):
        return {"root_node_id": root.id, "slot_ids": ids, "count": count}
    from .model import Rect
    from .item_slots import create_item_slot

    with session.transaction("Ajustar faixa Multi Itens"):
        if count < len(ids):
            for sid in ids[count:]:
                child_id = str(page.slots[sid].metadata["root_node_id"])
                page.remove_node(child_id, recursive=True)
            ids = ids[:count]
        while len(ids) < count:
            slot = create_item_slot(session, "multi-cell-beta44",
                                    x=root.rect.x, y=root.rect.y)
            child_root_id = str(slot.metadata["root_node_id"])
            child_root = page.node(child_root_id)
            page.roots.remove(child_root_id)
            child_root.parent_id = root.id
            root.children.append(child_root_id)
            slot.metadata["multi_parent_id"] = root.id
            slot.metadata["price_mode"] = root.metadata.get("price_mode", "auto")
            ids.append(slot.id)

        bounds = root.rect.normalized()
        width = bounds.width / count
        for index, sid in enumerate(ids):
            slot = page.slots[sid]
            slot.metadata["multi_parent_id"] = root.id
            slot.metadata["multi_index"] = index
            slot.metadata["multi_count"] = count
            child_id = str(slot.metadata["root_node_id"])
            child = page.node(child_id)
            current = child.rect.normalized()
            session._scale_tree(child_id, current, Rect(
                bounds.x + index * width, bounds.y, width, bounds.height))

        # Rebuild ONLY dividers; do not touch the common rounded ribbon.
        for nid in list(root.children):
            item = page.node(nid)
            if item is not None and item.name.startswith("Divisor "):
                page.remove_node(nid)
        for index in range(1, count):
            divider = GraphicsNode(
                kind=NodeKind.RECT,
                name=f"Divisor {index}",
                transform=Transform(
                    x=bounds.x + index * width - 1.2,
                    y=bounds.y + bounds.height * .14,
                    width=2.4, height=bounds.height * .47),
                z_index=8,
                style={"fill": "#105594", "stroke_width": 0},
                metadata={"multi_item_decoration": True},
            )
            # Keep the currently selected campaign theme.
            footer = next((page.node(nid) for nid in root.children
                           if page.node(nid).name == "Faixa azul contínua"), None)
            if footer is not None:
                divider.style["fill"] = footer.style.get("fill", "#105594")
            page.add_node(divider, parent_id=root.id)
        root.metadata["multi_count"] = count
        root.metadata["child_slot_ids"] = ids
        root.name = f"Smart Slot Multi Itens — {count} produtos"
    session.selection = {root.id}
    session.anchor_id = root.id
    return {"root_node_id": root.id, "slot_ids": ids, "count": count}
