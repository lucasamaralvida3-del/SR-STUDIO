from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.autosave import AutosaveManager, RecoveryPoint, default_autosave_root
from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.package import register_local_asset


def test_autosave_keeps_generations_and_recovers(tmp_path):
    manager = AutosaveManager(tmp_path, generations=2)
    document = GraphicsDocument(name="Campanha")
    for index in range(3):
        document.metadata["revision"] = index
        manager.save(document)
    points = manager.list_recovery_points(document.id)
    assert len(points) == 2
    restored = manager.recover(points[0])
    assert restored.id == document.id
    assert restored.name == "Campanha"
    assert restored.metadata["revision"] == 2


def test_back_to_back_autosaves_have_distinct_generation_paths(tmp_path):
    manager = AutosaveManager(tmp_path, generations=4)
    document = GraphicsDocument(name="Gerações únicas")

    document.metadata["revision"] = 1
    first = manager.save(document)
    document.metadata["revision"] = 2
    second = manager.save(document)

    assert first != second
    assert first.name.endswith("Z.srscene")
    assert second.name.endswith("Z.srscene")
    # O trecho fracionário evita que duas gerações dentro do mesmo segundo
    # compartilhem o mesmo alvo e misturem conteúdo/journal concorrentes.
    assert "." in first.stem and len(first.stem.rsplit(".", 1)[1].removesuffix("Z")) == 6
    assert "." in second.stem and len(second.stem.rsplit(".", 1)[1].removesuffix("Z")) == 6
    assert manager.recover(manager.latest(document.id)).metadata["revision"] == 2


def test_corrupt_generation_does_not_consume_valid_retention_slot(tmp_path):
    manager = AutosaveManager(tmp_path, generations=2)
    document = GraphicsDocument(name="Campanha")
    document.metadata["revision"] = 1
    first = manager.save(document)

    corrupt = first.parent / "99999999T999999.999999Z.srscene"
    corrupt.write_bytes(b"broken autosave")

    document.metadata["revision"] = 2
    manager.save(document)
    document.metadata["revision"] = 3
    manager.save(document)

    points = manager.list_recovery_points(document.id)
    assert len(points) == 2
    assert [manager.recover(point).metadata["revision"] for point in points] == [3, 2]
    assert corrupt.exists(), "arquivo inválido é preservado para diagnóstico, mas não conta na retenção"


def test_recover_rejects_recovery_point_from_other_document(tmp_path):
    manager = AutosaveManager(tmp_path)
    original = GraphicsDocument(name="Encarte A")
    path = manager.save(original)
    point = RecoveryPoint(
        path=path,
        document_id="doc_diferente",
        document_name="Encarte B",
        saved_at=manager.latest(original.id).saved_at,
        size=Path(path).stat().st_size,
    )

    with pytest.raises(ValueError, match="não pertence"):
        manager.recover(point)


def test_latest_skips_corrupt_newest_file(tmp_path):
    manager = AutosaveManager(tmp_path)
    document = GraphicsDocument(name="Campanha")
    valid = manager.save(document)
    corrupt = valid.parent / "99999999T999999.999999Z.srscene"
    corrupt.write_bytes(b"broken")

    latest = manager.latest(document.id)

    assert latest is not None
    assert latest.path == valid


def test_autosave_embeds_local_assets_so_recovery_survives_missing_original(tmp_path):
    manager = AutosaveManager(tmp_path / "autosave")
    source = tmp_path / "produto.png"
    raw = b"fake-image-payload-for-package-test"
    source.write_bytes(raw)

    document = GraphicsDocument(name="Encarte com imagem")
    asset = register_local_asset(document, source, kind="image", mime="image/png")
    document.active_page.add_node(
        GraphicsNode(
            kind=NodeKind.IMAGE,
            name="Produto",
            asset_id=asset.id,
            transform=Transform(x=10, y=20, width=200, height=180),
        )
    )

    manager.save(document)
    point = manager.latest(document.id)
    assert point is not None
    source.unlink()

    restored = manager.recover(point, extract_assets_to=tmp_path / "recovered-assets")
    restored_asset = restored.assets[asset.id]

    assert Path(restored_asset.source).is_file()
    assert Path(restored_asset.source).read_bytes() == raw
    restored_node = next(iter(restored.active_page.nodes.values()))
    assert restored_node.asset_id == asset.id
    assert restored_node.metadata["package_asset_extracted"] is True


def test_default_autosave_root_is_dedicated_to_graphics2():
    root = default_autosave_root()

    assert root.name == "autosave-g2"
    assert root.parent.name == ".srstudio5"
