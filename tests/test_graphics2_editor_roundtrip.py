from __future__ import annotations

from pathlib import Path

from srstudio.graphics2 import GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, Transform
from srstudio.graphics2.package import load_package, register_local_asset, save_package


def test_editor_roundtrip_preserves_multipage_visual_state_and_embedded_image(tmp_path):
    source = tmp_path / "produto.png"
    raw = b"roundtrip-image-payload"
    source.write_bytes(raw)

    document = GraphicsDocument(name="Round-trip produção")
    asset = register_local_asset(document, source, kind="image", mime="image/png")
    session = GraphicsSession(document)
    page = session.page
    page.name = "Frente"
    page.guides_x = [100.0, 540.0]
    page.guides_y = [80.0]
    page.metadata["editor_note"] = "preservar"

    group = GraphicsNode(
        kind=NodeKind.GROUP,
        name="Bloco visual",
        transform=Transform(x=80, y=120, width=520, height=400, rotation=7.5),
        z_index=9,
        opacity=0.92,
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        asset_id=asset.id,
        transform=Transform(x=110, y=150, width=260, height=240, rotation=3.0),
        z_index=10,
        style={
            "fit": "cover",
            "focus_x": 0.37,
            "focus_y": 0.62,
            "zoom": 1.35,
            "crop": {"l": 0.08, "t": 0.03, "r": 0.12, "b": 0.05},
            "flip_x": True,
        },
        metadata={"editor_custom": {"keep": True}},
    )
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Chamada",
        text="OFERTA ESPECIAL",
        transform=Transform(x=120, y=420, width=430, height=70, rotation=1.5),
        z_index=11,
        style={
            "font_family": "Arial",
            "font_size": 34.0,
            "font_weight": 700,
            "align": "center",
            "color": "#112233",
        },
    )
    page.add_node(group)
    page.add_node(image, parent_id=group.id)
    page.add_node(text, parent_id=group.id)

    original_page_id = page.id
    original_node_ids = set(page.nodes)
    duplicate_page_id = session.add_page(name="Verso", duplicate_active=True)
    duplicate = document.active_page
    duplicate_text = next(node for node in duplicate.nodes.values() if node.name == "Chamada")
    duplicate_text.text = "VERSO INDEPENDENTE"

    assert duplicate_page_id != original_page_id
    assert set(duplicate.nodes).isdisjoint(original_node_ids)
    assert document.page(original_page_id).nodes[text.id].text == "OFERTA ESPECIAL"

    page_ids_before = [item.id for item in document.pages]
    node_ids_before = {item.id: set(item.nodes) for item in document.pages}
    active_before = document.active_page_id
    package = save_package(document, tmp_path / "projeto.srscene", embed_local_assets=True)
    source.unlink()

    loaded = load_package(package, extract_assets_to=tmp_path / "extracted")

    assert loaded.id == document.id
    assert loaded.name == document.name
    assert [item.id for item in loaded.pages] == page_ids_before
    assert loaded.active_page_id == active_before
    assert {item.id: set(item.nodes) for item in loaded.pages} == node_ids_before

    loaded_front = loaded.page(original_page_id)
    assert loaded_front is not None
    assert loaded_front.guides_x == [100.0, 540.0]
    assert loaded_front.guides_y == [80.0]
    assert loaded_front.metadata["editor_note"] == "preservar"

    loaded_group = loaded_front.nodes[group.id]
    loaded_image = loaded_front.nodes[image.id]
    loaded_text = loaded_front.nodes[text.id]
    assert loaded_group.children == [image.id, text.id]
    assert loaded_image.parent_id == group.id
    assert loaded_text.parent_id == group.id
    assert loaded_group.z_index == 9
    assert loaded_group.opacity == 0.92
    assert loaded_group.transform.rotation == 7.5
    assert loaded_image.transform.rotation == 3.0
    assert loaded_text.transform.rotation == 1.5
    assert loaded_text.text == "OFERTA ESPECIAL"
    assert loaded_text.style["font_family"] == "Arial"
    assert loaded_text.style["color"] == "#112233"
    assert loaded_image.style["crop"] == {"l": 0.08, "t": 0.03, "r": 0.12, "b": 0.05}
    assert loaded_image.style["focus_x"] == 0.37
    assert loaded_image.style["focus_y"] == 0.62
    assert loaded_image.style["zoom"] == 1.35
    assert loaded_image.style["flip_x"] is True
    assert loaded_image.metadata["editor_custom"] == {"keep": True}

    loaded_asset = loaded.assets[asset.id]
    extracted = Path(loaded_asset.source)
    assert extracted.is_file()
    assert extracted.read_bytes() == raw

    loaded_duplicate = loaded.page(duplicate_page_id)
    assert loaded_duplicate is not None
    loaded_duplicate_text = next(node for node in loaded_duplicate.nodes.values() if node.name == "Chamada")
    assert loaded_duplicate_text.text == "VERSO INDEPENDENTE"
    assert loaded_front.nodes[text.id].text == "OFERTA ESPECIAL"
