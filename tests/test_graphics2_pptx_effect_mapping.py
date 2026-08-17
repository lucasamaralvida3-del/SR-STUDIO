from __future__ import annotations

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_effect_mapping import map_pptx_effects_to_document


def _shape(*, name: str = "Preço principal", kind: str = "shape") -> dict:
    return {
        "slide": 1,
        "shape_id": "42",
        "shape_name": name,
        "shape_kind": kind,
        "advanced_effects": 2,
        "alpha_modifiers": 1,
        "gradient_fills": 1,
        "pattern_fills": 0,
        "outer_shadows": 1,
        "inner_shadows": 0,
        "glows": 0,
        "reflections": 0,
        "soft_edges": 0,
        "blurs": 0,
        "effect_dags": 0,
        "scene_3d": 0,
        "shape_3d": 0,
        "linear_gradient": {
            "type": "linear",
            "angle": 0.0,
            "scaled": True,
            "stops": [
                {"position": 0.0, "color": "#FF0000", "alpha": 1.0},
                {"position": 1.0, "color": "#0000FF", "alpha": 1.0},
            ],
        },
        "outer_shadow": {
            "type": "outer",
            "color": "#000000",
            "alpha": 0.4,
            "blur": 3.0,
            "distance": 4.0,
            "direction": 45.0,
            "rot_with_shape": False,
        },
    }


def test_maps_effect_shape_by_preserved_source_name_and_annotates_node() -> None:
    document = GraphicsDocument(name="Quinta Filé")
    node = GraphicsNode(
        id="price",
        kind=NodeKind.TEXT,
        name="Preço",
        transform=Transform(x=10, y=10, width=120, height=80),
        metadata={"source_name": "Preço principal"},
    )
    document.active_page.add_node(node)
    document.metadata["pptx_effects"] = {"shapes": [_shape()]}

    report = map_pptx_effects_to_document(document)

    assert report.source_shapes == 1
    assert report.mapped_shapes == 1
    assert report.coverage == 1.0
    assert report.ambiguous_shapes == 0
    assert report.missing_shapes == 0
    assert report.applied_gradients == 0
    assert report.applied_outer_shadows == 1
    assert report.mappings[0].node_id == "price"
    assert node.metadata["pptx_shape_id"] == "42"
    assert node.metadata["pptx_shape_name"] == "Preço principal"
    assert node.metadata["pptx_effects"]["gradient_fills"] == 1
    assert node.style["shadow"]["alpha"] == 0.4
    assert "gradient" not in node.style
    assert document.metadata["pptx_effect_mapping"]["coverage"] == 1.0
    assert document.metadata["pptx_effect_mapping"]["applied_outer_shadows"] == 1


def test_applies_gradient_and_shadow_to_renderable_shape_style() -> None:
    document = GraphicsDocument(name="Renderable effects")
    node = GraphicsNode(
        id="banner",
        kind=NodeKind.RECT,
        name="Faixa",
        transform=Transform(x=10, y=10, width=400, height=120),
        metadata={"source_name": "Faixa decorativa"},
        style={"fill": "#FFFFFF"},
    )
    document.active_page.add_node(node)
    document.metadata["pptx_effects"] = {"shapes": [_shape(name="Faixa decorativa")]}

    report = map_pptx_effects_to_document(document)

    assert report.mapped_shapes == 1
    assert report.applied_gradients == 1
    assert report.applied_outer_shadows == 1
    assert node.style["gradient"]["type"] == "linear"
    assert node.style["gradient"]["stops"][0]["color"] == "#FF0000"
    assert node.style["shadow"]["type"] == "outer"
    assert node.style["shadow"]["direction"] == 45.0


def test_preserves_existing_editor_effect_styles() -> None:
    document = GraphicsDocument(name="Existing styles")
    node = GraphicsNode(
        id="banner",
        kind=NodeKind.RECT,
        name="Faixa",
        transform=Transform(width=400, height=120),
        metadata={"source_name": "Faixa decorativa"},
        style={
            "gradient": {"type": "linear", "stops": [{"position": 0.0, "color": "#00FF00"}, {"position": 1.0, "color": "#00FFFF"}]},
            "shadow": {"type": "outer", "color": "#123456", "alpha": 1.0},
        },
    )
    document.active_page.add_node(node)
    document.metadata["pptx_effects"] = {"shapes": [_shape(name="Faixa decorativa")]}

    report = map_pptx_effects_to_document(document)

    assert report.mapped_shapes == 1
    assert report.applied_gradients == 0
    assert report.applied_outer_shadows == 0
    assert node.style["gradient"]["stops"][0]["color"] == "#00FF00"
    assert node.style["shadow"]["color"] == "#123456"


def test_does_not_guess_when_source_name_is_ambiguous() -> None:
    document = GraphicsDocument(name="Ambiguous")
    for node_id in ("one", "two"):
        document.active_page.add_node(
            GraphicsNode(
                id=node_id,
                kind=NodeKind.TEXT,
                name="Duplicado",
                transform=Transform(width=100, height=30),
                metadata={"source_name": "Duplicado"},
            )
        )
    document.metadata["pptx_effects"] = {"shapes": [_shape(name="Duplicado")]}

    report = map_pptx_effects_to_document(document)

    assert report.mapped_shapes == 0
    assert report.ambiguous_shapes == 1
    assert report.coverage == 0.0
    assert report.issues[0].code == "PPTX_EFFECT_SHAPE_AMBIGUOUS"
    assert all("pptx_effects" not in node.metadata for node in document.active_page.nodes.values())


def test_picture_kind_breaks_same_name_tie_in_favor_of_image_node() -> None:
    document = GraphicsDocument(name="Picture tie")
    text = GraphicsNode(
        id="label",
        kind=NodeKind.TEXT,
        name="Produto 1",
        transform=Transform(width=100, height=40),
        metadata={"source_name": "Produto 1"},
    )
    image = GraphicsNode(
        id="photo",
        kind=NodeKind.IMAGE,
        name="Produto 1",
        transform=Transform(width=200, height=200),
        metadata={"source_name": "Produto 1"},
    )
    document.active_page.add_node(text)
    document.active_page.add_node(image)
    document.metadata["pptx_effects"] = {"shapes": [_shape(name="Produto 1", kind="picture")]}

    report = map_pptx_effects_to_document(document)

    assert report.mapped_shapes == 1
    assert report.mappings[0].node_id == "photo"
    assert image.metadata["pptx_shape_id"] == "42"
    assert "pptx_shape_id" not in text.metadata
    assert "gradient" not in image.style
    assert "shadow" not in image.style


def test_empty_effect_inventory_has_full_coverage_and_no_issues() -> None:
    document = GraphicsDocument(name="No effects")
    document.metadata["pptx_effects"] = {"shapes": []}

    report = map_pptx_effects_to_document(document)

    assert report.source_shapes == 0
    assert report.mapped_shapes == 0
    assert report.applied_gradients == 0
    assert report.applied_outer_shadows == 0
    assert report.coverage == 1.0
    assert report.issues == []