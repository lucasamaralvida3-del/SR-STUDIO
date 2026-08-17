from __future__ import annotations

"""Layout automático e preenchimento inteligente para o SR Graphics Engine 2."""

from dataclasses import dataclass
from math import ceil, sqrt
from typing import Iterable, Sequence

from .import_bridge import CanvaBindingService
from .model import GraphicsNode, NodeKind
from .operations import GraphicsSession


@dataclass(slots=True)
class LayoutOptions:
    margin_left: float = 36.0
    margin_top: float = 36.0
    margin_right: float = 36.0
    margin_bottom: float = 36.0
    gap_x: float = 20.0
    gap_y: float = 20.0
    header_reserved: float = 0.0
    footer_reserved: float = 0.0
    columns: int | None = None
    keep_size: bool = False
    fill_ratio: float = 0.92


@dataclass(slots=True, frozen=True)
class LayoutResult:
    moved: int
    columns: int
    rows: int
    cell_width: float
    cell_height: float


class SmartLayoutEngine:
    """Arranjo determinístico de cards/grupos sem depender do renderer."""

    @staticmethod
    def auto_grid(
        session: GraphicsSession,
        node_ids: Iterable[str] | None = None,
        *,
        options: LayoutOptions | None = None,
    ) -> LayoutResult:
        options = options or LayoutOptions()
        nodes = SmartLayoutEngine._layout_nodes(session, node_ids)
        if not nodes:
            return LayoutResult(0, 0, 0, 0.0, 0.0)
        page = session.page
        usable_width = max(1.0, page.width - options.margin_left - options.margin_right)
        usable_height = max(
            1.0,
            page.height
            - options.margin_top
            - options.margin_bottom
            - options.header_reserved
            - options.footer_reserved,
        )
        columns = options.columns or SmartLayoutEngine._suggest_columns(len(nodes), usable_width, usable_height)
        columns = min(len(nodes), max(1, int(columns)))
        rows = ceil(len(nodes) / columns)
        cell_width = max(1.0, (usable_width - options.gap_x * (columns - 1)) / columns)
        cell_height = max(1.0, (usable_height - options.gap_y * (rows - 1)) / rows)
        with session.transaction("Layout automático"):
            for index, node in enumerate(nodes):
                row, column = divmod(index, columns)
                cell_x = options.margin_left + column * (cell_width + options.gap_x)
                cell_y = options.margin_top + options.header_reserved + row * (cell_height + options.gap_y)
                SmartLayoutEngine._place_tree(
                    session,
                    node,
                    cell_x,
                    cell_y,
                    cell_width,
                    cell_height,
                    keep_size=options.keep_size,
                    fill_ratio=options.fill_ratio,
                )
        return LayoutResult(len(nodes), columns, rows, cell_width, cell_height)

    @staticmethod
    def auto_grid_by_category(
        session: GraphicsSession,
        node_ids: Iterable[str] | None = None,
        *,
        options: LayoutOptions | None = None,
    ) -> LayoutResult:
        nodes = SmartLayoutEngine._layout_nodes(session, node_ids)
        nodes.sort(key=lambda node: (SmartLayoutEngine._category(node), node.name.casefold(), node.id))
        return SmartLayoutEngine.auto_grid(session, [node.id for node in nodes], options=options)

    @staticmethod
    def fill_smart_slots(
        session: GraphicsSession,
        products: Sequence[dict],
        *,
        overwrite: bool = False,
    ) -> int:
        slots = sorted(
            session.page.slots.values(),
            key=lambda slot: SmartLayoutEngine._slot_sort_key(session, slot),
        )
        available = [slot for slot in slots if overwrite or not slot.product_id]
        applied = 0
        for slot, product in zip(available, products):
            if slot.locked:
                continue
            if slot.metadata.get("source") == "canva-smart-slot":
                changed = CanvaBindingService.bind(session, slot.id, dict(product))
                applied += int(changed)
            else:
                session.bind_product(slot.id, dict(product))
                applied += 1
        return applied

    @staticmethod
    def _layout_nodes(session: GraphicsSession, node_ids: Iterable[str] | None) -> list[GraphicsNode]:
        page = session.page
        ids = set(node_ids or session.selection)
        if ids:
            candidates = [page.nodes[node_id] for node_id in ids if node_id in page.nodes]
            roots = [node for node in candidates if node.parent_id not in ids]
        else:
            roots = [page.nodes[node_id] for node_id in page.roots if node_id in page.nodes]
        preferred = [
            node
            for node in roots
            if not node.locked
            and node.visible
            and node.kind in {NodeKind.GROUP, NodeKind.PRODUCT_CARD, NodeKind.RECT, NodeKind.IMAGE, NodeKind.TEXT}
            and not bool(node.metadata.get("fidelity_layer"))
        ]
        return sorted(preferred, key=lambda node: (node.z_index, node.id))

    @staticmethod
    def _suggest_columns(count: int, width: float, height: float) -> int:
        if count <= 1:
            return 1
        aspect = max(0.25, width / max(height, 1.0))
        suggested = round(sqrt(count * aspect))
        return max(1, min(count, suggested))

    @staticmethod
    def _place_tree(
        session: GraphicsSession,
        node: GraphicsNode,
        cell_x: float,
        cell_y: float,
        cell_width: float,
        cell_height: float,
        *,
        keep_size: bool,
        fill_ratio: float,
    ) -> None:
        t = node.transform
        old_x, old_y, old_w, old_h = t.x, t.y, max(t.width, 1.0), max(t.height, 1.0)
        if keep_size:
            scale = min(1.0, cell_width / old_w, cell_height / old_h)
        else:
            scale = min(cell_width / old_w, cell_height / old_h) * max(0.1, min(1.0, fill_ratio))
        new_w, new_h = old_w * scale, old_h * scale
        new_x = cell_x + (cell_width - new_w) / 2.0
        new_y = cell_y + (cell_height - new_h) / 2.0
        tree_ids = [node.id, *session.page.descendants(node.id)]
        for current_id in tree_ids:
            current = session.page.node(current_id)
            if current is None or current.locked:
                continue
            ct = current.transform
            rel_x = (ct.x - old_x) / old_w
            rel_y = (ct.y - old_y) / old_h
            rel_w = ct.width / old_w
            rel_h = ct.height / old_h
            ct.x = new_x + rel_x * new_w
            ct.y = new_y + rel_y * new_h
            ct.width = max(0.1, rel_w * new_w)
            ct.height = max(0.1, rel_h * new_h)
        t.x, t.y, t.width, t.height = new_x, new_y, new_w, new_h

    @staticmethod
    def _category(node: GraphicsNode) -> str:
        snapshot = dict(node.metadata.get("product_snapshot") or {})
        return str(snapshot.get("category") or node.metadata.get("category") or "SEM CATEGORIA").casefold()

    @staticmethod
    def _slot_sort_key(session: GraphicsSession, slot) -> tuple[float, float, str]:
        rects = [session.page.node(node_id).rect for node_id in slot.node_by_role.values() if session.page.node(node_id)]
        if not rects:
            return (float("inf"), float("inf"), slot.id)
        x = min(rect.x for rect in rects)
        y = min(rect.y for rect in rects)
        return (round(y, 3), round(x, 3), slot.id)
