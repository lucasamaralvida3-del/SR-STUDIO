from __future__ import annotations

from pathlib import Path

import srstudio

from srstudio.graphics2.import_bridge import CanvaBindingService
from srstudio.graphics2.model import (
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    GraphicsPage,
    NodeKind,
    SmartSlot,
    Transform,
)
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.smart_slot_geometry import refresh_smart_slot_geometry


def _node(
    node_id: str,
    kind: NodeKind,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    text: str = "",
    visible: bool = True,
) -> GraphicsNode:
    return GraphicsNode(
        id=node_id,
        kind=kind,
        name=node_id,
        transform=Transform(x=x, y=y, width=width, height=height),
        text=text,
        visible=visible,
    )


def _add_card(
    page: GraphicsPage,
    index: int,
    x: float,
    y: float,
    *,
    group_width: float = 310,
    shared_node_id: str = "",
) -> SmartSlot:
    prefix = f"c{index}"
    group = _node(f"{prefix}-group", NodeKind.GROUP, x - 55, y - 50, group_width, 285)
    page.add_node(group)
    image = _node(f"{prefix}-image", NodeKind.IMAGE, x, y, 90, 95)
    name = _node(f"{prefix}-name", NodeKind.TEXT, x, y + 102, 145, 30, text=f"PRODUTO VISUAL {index}")
    currency = _node(f"{prefix}-currency", NodeKind.TEXT, x + 5, y + 145, 25, 24, text="R$")
    reais = _node(f"{prefix}-reais", NodeKind.TEXT, x + 32, y + 135, 60, 42, text=str(index * 10))
    cents = _node(f"{prefix}-cents", NodeKind.TEXT, x + 92, y + 138, 35, 26, text=",99")
    unit = _node(f"{prefix}-unit", NodeKind.TEXT, x + 92, y + 164, 35, 20, text="/UN")
    hidden_limit = _node(f"{prefix}-limit", NodeKind.TEXT, x - 80, y + 230, 260, 24, text="LIMITE", visible=False)
    decoration = _node(f"{prefix}-decor", NodeKind.RECT, x - 8, y - 8, 170, 205)
    for node in (image, name, currency, reais, cents, unit, hidden_limit, decoration):
        page.add_node(node, group.id)
    if shared_node_id and shared_node_id in page.nodes:
        page.nodes[shared_node_id].parent_id = group.id

    slot = SmartSlot(
        id=f"slot-{index}",
        name=f"Produto {index}",
        page_id=page.id,
        node_by_role={
            BindingRole.IMAGE.value: image.id,
            BindingRole.NAME.value: name.id,
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: reais.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
            BindingRole.LIMIT.value: hidden_limit.id,
        },
        product_id=f"product-{index}",
        metadata={
            "semantic_product_card_id": f"card-{index}",
            "product_snapshot": {"id": f"product-{index}", "display_name": f"PRODUTO VISUAL {index}"},
        },
    )
    page.slots[slot.id] = slot
    content = [image.id, name.id, currency.id, reais.id, cents.id, unit.id, hidden_limit.id, decoration.id]
    page.metadata.setdefault("semantic_blocks", {})[f"card-{index}"] = {
        "id": f"card-{index}",
        "kind": "product_card",
        "slot_id": slot.id,
        "members": [group.id],
        "roles": {},
        "bounds": {
            "x": group.transform.x,
            "y": group.transform.y,
            "width": group.transform.width,
            "height": group.transform.height,
        },
        "metadata": {
            "source_group_id": group.id,
            "content_members": content,
            "preserve_source_geometry": True,
        },
    }
    return slot


def _five_card_document() -> GraphicsDocument:
    page = GraphicsPage(id="page-smart", name="Página Smart", width=1080, height=1350)
    for index, (x, y) in enumerate(
        [(70, 180), (360, 180), (650, 180), (215, 590), (520, 590)],
        start=1,
    ):
        _add_card(page, index, x, y)
    return GraphicsDocument(id="doc-smart", name="Smart Slots", pages=[page], active_page_id=page.id)


def _intersection_ratio(a: dict, b: dict) -> float:
    left = max(a["x"], b["x"])
    top = max(a["y"], b["y"])
    right = min(a["x"] + a["width"], b["x"] + b["width"])
    bottom = min(a["y"] + a["height"], b["y"] + b["height"])
    overlap = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = max(1.0, a["width"] * a["height"])
    area_b = max(1.0, b["width"] * b["height"])
    return overlap / min(area_a, area_b)


def test_group_bounds_are_not_used_as_smart_slot_interaction_bounds():
    document = _five_card_document()
    page = document.active_page
    original = dict(page.metadata["semantic_blocks"]["card-1"]["bounds"])

    report = refresh_smart_slot_geometry(document)
    effective = page.slots["slot-1"].metadata["effective_bounds"]

    assert report.slots == 5
    assert effective != original
    assert effective["width"] < original["width"]
    assert effective["height"] < original["height"]
    assert page.nodes["c1-group"].transform.x == original["x"]
    assert page.nodes["c1-group"].transform.width == original["width"]
    assert page.slots["slot-1"].metadata["geometry_source"] == "bindings+exclusive-card-members"


def test_hidden_optional_binding_does_not_inflate_effective_bounds():
    document = _five_card_document()
    page = document.active_page
    refresh_smart_slot_geometry(document)

    bounds = page.slots["slot-1"].metadata["effective_bounds"]
    hidden = page.nodes["c1-limit"].rect.normalized()

    assert bounds["y"] + bounds["height"] < hidden.bottom


def test_effective_bounds_remove_overlap_created_by_large_group_boxes():
    page = GraphicsPage(id="overlap-page", width=800, height=600)
    first = _add_card(page, 1, 100, 150, group_width=390)
    second = _add_card(page, 2, 330, 150, group_width=390)
    document = GraphicsDocument(id="overlap-doc", pages=[page], active_page_id=page.id)

    before_a = page.metadata["semantic_blocks"]["card-1"]["bounds"]
    before_b = page.metadata["semantic_blocks"]["card-2"]["bounds"]
    before = _intersection_ratio(before_a, before_b)
    assert before > 0.25

    report = refresh_smart_slot_geometry(document)
    after_a = first.metadata["effective_bounds"]
    after_b = second.metadata["effective_bounds"]
    after = _intersection_ratio(after_a, after_b)

    assert after < before
    assert after <= 0.12
    assert report.significant_overlaps == 0
    assert first.metadata["slot_overlap_ratio"] <= 0.12
    assert second.metadata["slot_overlap_ratio"] <= 0.12


def test_display_index_tracks_visual_card_order_not_dictionary_order():
    document = _five_card_document()
    page = document.active_page
    page.slots = dict(reversed(list(page.slots.items())))

    refresh_smart_slot_geometry(document)

    ordered = sorted(page.slots.values(), key=lambda slot: slot.metadata["display_index"])
    assert [slot.id for slot in ordered] == ["slot-1", "slot-2", "slot-3", "slot-4", "slot-5"]
    assert [slot.metadata["display_label"] for slot in ordered] == [
        "Produto 1", "Produto 2", "Produto 3", "Produto 4", "Produto 5"
    ]


def test_five_card_binding_updates_only_semantic_roles_and_keeps_decoration():
    document = _five_card_document()
    page = document.active_page
    session = GraphicsSession(document)

    for index in range(1, 6):
        slot = page.slots[f"slot-{index}"]
        decoration = page.nodes[f"c{index}-decor"]
        decoration_before = decoration.to_dict() if hasattr(decoration, "to_dict") else (
            decoration.transform.x,
            decoration.transform.y,
            decoration.transform.width,
            decoration.transform.height,
            dict(decoration.style),
        )
        product = {
            "id": f"replacement-{index}",
            "display_name": f"NOVO PRODUTO {index}",
            "price": f"{20 + index}.49",
            "unit": "KG",
            "image_path": f"C:/BancoSR/produto-{index}.png",
        }
        assert CanvaBindingService.bind(session, slot.id, product)
        assert slot.product_id == f"replacement-{index}"
        assert page.nodes[f"c{index}-name"].text == f"NOVO PRODUTO {index}"
        assert page.nodes[f"c{index}-currency"].text == "R$"
        assert page.nodes[f"c{index}-reais"].text == str(20 + index)
        assert page.nodes[f"c{index}-cents"].text == ",49"
        assert page.nodes[f"c{index}-unit"].text == "/KG"
        assert page.nodes[f"c{index}-image"].metadata["bound_image_source"].endswith(f"produto-{index}.png")
        decoration_after = decoration.to_dict() if hasattr(decoration, "to_dict") else (
            decoration.transform.x,
            decoration.transform.y,
            decoration.transform.width,
            decoration.transform.height,
            dict(decoration.style),
        )
        assert decoration_after == decoration_before


def test_smart_slot_ids_bounds_and_bindings_survive_save_reopen(tmp_path):
    document = _five_card_document()
    refresh_smart_slot_geometry(document)
    page = document.active_page
    before = {
        slot.id: {
            "product_id": slot.product_id,
            "node_by_role": dict(slot.node_by_role),
            "bounds": dict(slot.metadata["effective_bounds"]),
            "display_index": slot.metadata["display_index"],
        }
        for slot in page.slots.values()
    }

    target = save_package(document, tmp_path / "smart-slots.srscene", embed_local_assets=False)
    restored = load_package(target)
    restored_page = restored.active_page
    after = {
        slot.id: {
            "product_id": slot.product_id,
            "node_by_role": dict(slot.node_by_role),
            "bounds": dict(slot.metadata["effective_bounds"]),
            "display_index": slot.metadata["display_index"],
        }
        for slot in restored_page.slots.values()
    }

    assert after == before


def test_qml_smart_slot_overlays_are_interaction_only_and_export_is_not_qml_overlay():
    qml = (Path(srstudio.__file__).with_name("graphics2") / "qml" / "GraphicsEditor.qml").read_text(encoding="utf-8")

    assert "property bool smartSlotInspectionMode: false" in qml
    assert "slot.metadata.effective_bounds" in qml
    assert "visible: showSlotOverlay && width > 2 && height > 2" in qml
    assert "smartSlotInspectionMode || productDragActive || isSelectedSlot || isHoveredSlot" in qml
    assert "hoverEnabled: true" in qml
    assert "modelData.metadata.display_label" in qml
    assert 'Component.onCompleted: if (count > 0) selectedSlotId = currentValue' not in qml
    # O export usa qt_renderer a partir do GraphicsDocument, não o QML do editor.
    # Manter o overlay exclusivamente neste arquivo garante que Produto N/bordas
    # não existam como nodes serializados/renderizáveis.
    assert "SOLTAR PRODUTO AQUI" in qml
