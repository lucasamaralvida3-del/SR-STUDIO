from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.image_replace import normalize_local_image_source, replace_image_source
from srstudio.graphics2.model import AssetRef, BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession


def _png(path: Path) -> Path:
    # O serviço valida contrato/caminho; o conteúdo será validado pelo renderer.
    path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    return path


def _session(tmp_path: Path) -> tuple[GraphicsSession, GraphicsNode, SmartSlot, Path]:
    old = _png(tmp_path / "old.png")
    document = GraphicsDocument(name="Replace image")
    asset = AssetRef(kind="image", source=str(old.resolve()))
    document.assets[asset.id] = asset
    node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto",
        asset_id=asset.id,
        transform=Transform(x=120, y=180, width=320, height=260, rotation=13),
        z_index=77,
        opacity=0.82,
        style={
            "fit": "cover",
            "crop": {"l": 0.1, "t": 0.05, "r": 0.08, "b": 0.04},
            "focus_x": 0.35,
            "focus_y": 0.62,
            "zoom": 1.4,
            "flip_x": True,
        },
        metadata={"bound_image_source": str(old.resolve())},
    )
    document.active_page.add_node(node)
    slot = SmartSlot(
        name="Produto 1",
        page_id=document.active_page.id,
        node_by_role={BindingRole.IMAGE.value: node.id},
        product_id="p1",
    )
    document.active_page.slots[slot.id] = slot
    return GraphicsSession(document), node, slot, old


def test_replace_image_preserves_design_slot_identity_and_roundtrips_undo_redo(tmp_path):
    session, node, slot, old = _session(tmp_path)
    new = _png(tmp_path / "new product.png")
    before_transform = (
        node.transform.x,
        node.transform.y,
        node.transform.width,
        node.transform.height,
        node.transform.rotation,
    )
    before_style = dict(node.style)
    before_z = node.z_index
    before_opacity = node.opacity
    before_asset = node.asset_id

    result = replace_image_source(session, node.id, new.as_uri())

    current = session.page.node(node.id)
    assert current is not None
    assert result.node_id == node.id
    assert result.source == str(new.resolve())
    assert result.asset_id == current.asset_id
    assert result.asset_id != before_asset
    assert current.metadata["bound_image_source"] == str(new.resolve())
    assert current.metadata["manual_image_override"] is True
    assert (
        current.transform.x,
        current.transform.y,
        current.transform.width,
        current.transform.height,
        current.transform.rotation,
    ) == before_transform
    assert current.style == before_style
    assert current.z_index == before_z
    assert current.opacity == before_opacity
    assert session.page.slots[slot.id].node_by_role[BindingRole.IMAGE.value] == node.id

    assert session.undo()
    restored = session.page.node(node.id)
    assert restored is not None
    assert restored.asset_id == before_asset
    assert restored.metadata["bound_image_source"] == str(old.resolve())
    assert "manual_image_override" not in restored.metadata
    assert session.page.slots[slot.id].node_by_role[BindingRole.IMAGE.value] == node.id

    assert session.redo()
    redone = session.page.node(node.id)
    assert redone is not None
    assert redone.metadata["bound_image_source"] == str(new.resolve())
    assert redone.asset_id == result.asset_id


def test_replace_image_reuses_registered_asset_for_same_file(tmp_path):
    session, node, _slot, _old = _session(tmp_path)
    replacement = _png(tmp_path / "replacement.webp")

    first = replace_image_source(session, node.id, str(replacement))
    asset_count = len(session.document.assets)
    second = replace_image_source(session, node.id, replacement.as_uri())

    assert first.reused_asset is False
    assert second.reused_asset is True
    assert second.asset_id == first.asset_id
    assert len(session.document.assets) == asset_count


def test_replace_image_rejects_missing_or_unsupported_file_without_history_entry(tmp_path):
    session, node, _slot, old = _session(tmp_path)
    original = session.document.to_dict()

    with pytest.raises(ValueError, match="Imagem não encontrada"):
        replace_image_source(session, node.id, str(tmp_path / "missing.png"))
    assert session.document.to_dict() == original
    assert not session.history.can_undo

    unsupported = tmp_path / "product.svg"
    unsupported.write_text("<svg/>", encoding="utf-8")
    with pytest.raises(ValueError, match="Formato de imagem não suportado"):
        replace_image_source(session, node.id, unsupported.as_uri())
    assert session.document.to_dict() == original
    assert not session.history.can_undo


def test_replace_image_rejects_non_image_node_and_locked_image(tmp_path):
    session, node, _slot, _old = _session(tmp_path)
    replacement = _png(tmp_path / "replacement.jpg")
    text = GraphicsNode(kind=NodeKind.TEXT, text="Produto", transform=Transform(width=100, height=30))
    session.page.add_node(text)

    with pytest.raises(ValueError, match="Selecione uma imagem"):
        replace_image_source(session, text.id, replacement.as_uri())

    node.locked = True
    with pytest.raises(ValueError, match="bloqueada"):
        replace_image_source(session, node.id, replacement.as_uri())


def test_normalize_local_image_source_accepts_file_url_and_rejects_remote_url(tmp_path):
    image = _png(tmp_path / "produto com espaço.png")
    assert normalize_local_image_source(image.as_uri()) == image.resolve()

    with pytest.raises(ValueError, match="somente arquivos locais"):
        normalize_local_image_source("https://example.com/produto.png")
