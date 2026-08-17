from __future__ import annotations

"""Context model for a focused, non-cluttered G2 properties inspector."""

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .model import GraphicsPage, NodeKind


@dataclass(slots=True, frozen=True)
class InspectorContext:
    target_type: str
    target_id: str
    title: str
    sections: tuple[str, ...]
    properties: tuple[str, ...]
    multi_selection: bool = False
    semantic: bool = False
    slot_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_GENERIC_SECTIONS = ("transform", "arrangement")
_GENERIC_PROPERTIES = (
    "x",
    "y",
    "width",
    "height",
    "rotation",
    "opacity",
    "visible",
    "locked",
    "z_index",
)


def inspector_context(page: GraphicsPage, selection: Iterable[str]) -> InspectorContext:
    """Return only properties relevant to the current editor selection."""
    selected = [str(item) for item in selection if str(item)]
    if not selected:
        return InspectorContext("page", page.id, page.name or "Página", ("page",), (
            "name",
            "width",
            "height",
            "background",
            "guides",
        ))

    if len(selected) > 1:
        return InspectorContext(
            "multi",
            "",
            f"{len(selected)} itens selecionados",
            ("transform", "arrangement", "alignment"),
            (
                "move",
                "opacity",
                "visible",
                "locked",
                "align_left",
                "align_center",
                "align_right",
                "align_top",
                "align_middle",
                "align_bottom",
                "distribute_horizontal",
                "distribute_vertical",
                "group",
                "delete",
            ),
            multi_selection=True,
        )

    target_id = selected[0]
    semantic = _semantic_block(page, target_id)
    if semantic is not None:
        kind = str(semantic.get("kind") or "semantic")
        slot_id = str(semantic.get("slot_id") or "")
        if kind == "product_card":
            return InspectorContext(
                "product_card",
                target_id,
                str(semantic.get("name") or "ProductCard"),
                ("product", "price", "image", "binding", "arrangement"),
                (
                    "product",
                    "name",
                    "price",
                    "unit",
                    "image_source",
                    "limit",
                    "app_price",
                    "replace_product",
                    "binding_confidence",
                    "locked",
                    "z_index",
                ),
                semantic=True,
                slot_id=slot_id,
            )
        if kind == "price_block":
            return InspectorContext(
                "price_block",
                target_id,
                str(semantic.get("name") or "PriceBlock"),
                ("price", "typography", "arrangement"),
                (
                    "price",
                    "currency",
                    "unit",
                    "font_family",
                    "font_size",
                    "color",
                    "opacity",
                    "locked",
                    "z_index",
                ),
                semantic=True,
                slot_id=slot_id,
            )

    node = page.node(target_id)
    if node is None:
        return InspectorContext("unknown", target_id, "Item", (), ())

    if node.kind is NodeKind.TEXT:
        return InspectorContext(
            "text",
            node.id,
            node.name or "Texto",
            ("text", "typography", *_GENERIC_SECTIONS),
            (
                "text",
                "font_family",
                "font_size",
                "font_weight",
                "italic",
                "color",
                "align",
                "vertical_align",
                "letter_spacing",
                "line_spacing",
                *_GENERIC_PROPERTIES,
            ),
        )

    if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
        return InspectorContext(
            "image",
            node.id,
            node.name or "Imagem",
            ("image", "crop", *_GENERIC_SECTIONS),
            (
                "replace_image",
                "fit",
                "zoom",
                "focus_x",
                "focus_y",
                "crop_left",
                "crop_top",
                "crop_right",
                "crop_bottom",
                "flip_x",
                "flip_y",
                "reset_framing",
                *_GENERIC_PROPERTIES,
            ),
        )

    if node.kind in {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.LINE, NodeKind.PATH}:
        return InspectorContext(
            "shape",
            node.id,
            node.name or "Forma",
            ("shape", *_GENERIC_SECTIONS),
            (
                "fill",
                "stroke",
                "stroke_width",
                "gradient",
                *_GENERIC_PROPERTIES,
            ),
        )

    if node.kind is NodeKind.GROUP:
        return InspectorContext(
            "group",
            node.id,
            node.name or "Grupo",
            ("group", *_GENERIC_SECTIONS),
            ("children", "ungroup", *_GENERIC_PROPERTIES),
        )

    return InspectorContext(
        str(getattr(node.kind, "value", node.kind)),
        node.id,
        node.name or "Item",
        _GENERIC_SECTIONS,
        _GENERIC_PROPERTIES,
    )


def _semantic_block(page: GraphicsPage, block_id: str) -> dict[str, Any] | None:
    raw = page.metadata.get("semantic_blocks")
    if not isinstance(raw, dict):
        return None
    block = raw.get(block_id)
    return dict(block) if isinstance(block, dict) else None
