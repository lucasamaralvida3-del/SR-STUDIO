from __future__ import annotations

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import AssetRef, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.operations import GraphicsSession


def test_router_replace_image_preserves_node_identity_and_supports_undo_redo(tmp_path):
    old = tmp_path / "old.png"
    new = tmp_path / "new.png"
    old.write_bytes(b"old")
    new.write_bytes(b"new")

    document = GraphicsDocument(name="Router replace image")
    asset = AssetRef(kind="image", source=str(old.resolve()))
    document.assets[asset.id] = asset
    node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        asset_id=asset.id,
        transform=Transform(x=40, y=50, width=280, height=240, rotation=7),
        z_index=21,
        style={"fit": "cover", "crop": {"l": 0.08, "t": 0.04, "r": 0.02, "b": 0.01}},
        metadata={"bound_image_source": str(old.resolve())},
    )
    document.active_page.add_node(node)
    router = GraphicsCommandRouter(GraphicsSession(document))
    router.dispatch({"name": "select", "node_id": node.id})

    before = document.active_page.node(node.id)
    geometry = before.transform
    old_asset_id = before.asset_id

    changed = router.dispatch({"name": "replace_image", "source": new.as_uri()})
    assert changed.ok and changed.changed
    assert changed.payload["node_id"] == node.id
    assert changed.payload["source"] == str(new.resolve())

    current = router.session.page.node(node.id)
    assert current is not None
    assert current.asset_id != old_asset_id
    assert current.transform == geometry
    assert current.z_index == 21
    assert current.style["fit"] == "cover"
    assert current.style["crop"] == {"l": 0.08, "t": 0.04, "r": 0.02, "b": 0.01}

    assert router.dispatch({"name": "undo"}).changed
    restored = router.session.page.node(node.id)
    assert restored is not None
    assert restored.asset_id == old_asset_id
    assert restored.metadata["bound_image_source"] == str(old.resolve())

    assert router.dispatch({"name": "redo"}).changed
    redone = router.session.page.node(node.id)
    assert redone is not None
    assert redone.metadata["bound_image_source"] == str(new.resolve())


def test_router_replace_image_returns_clear_error_without_mutating_scene(tmp_path):
    document = GraphicsDocument(name="Router replace image error")
    node = GraphicsNode(kind=NodeKind.IMAGE, transform=Transform(width=100, height=100))
    document.active_page.add_node(node)
    router = GraphicsCommandRouter(GraphicsSession(document))
    router.dispatch({"name": "select", "node_id": node.id})
    before = document.to_dict()

    result = router.dispatch({"name": "replace_image", "source": str(tmp_path / "missing.png")})

    assert not result.ok
    assert not result.changed
    assert "Imagem não encontrada" in result.message
    assert router.session.document.to_dict() == before
    assert not router.session.history.can_undo
