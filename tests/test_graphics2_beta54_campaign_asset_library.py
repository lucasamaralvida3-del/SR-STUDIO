"""Campaign artwork ZIP integration and malicious/archive regression tests."""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from srstudio.graphics2.campaign_asset_library import (
    PACK_FORMAT, import_campaign_pack, list_campaign_assets,
)
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.operations import GraphicsSession


def make_pack(path: Path, *, tamper=False, traversal=False):
    bg = b"example background content"
    seal = b"example transparent seal"
    background_path = "../escape.jpg" if traversal else "fundos/quarta-cafe.jpg"
    items = [
        {"path": background_path, "campaign_id": "quarta-cafe", "kind": "background",
         "name": "Fundo Quarta Café", "size": len(bg), "sha256": sha256(bg).hexdigest()},
        {"path": "selos/quarta-cafe.png", "campaign_id": "quarta-cafe",
         "kind": "seal", "name": "Selo Quarta Café", "size": len(seal),
         "sha256": sha256(seal).hexdigest()},
        {"path": "referencias/exemplo.jpg", "campaign_id": "quarta-cafe",
         "kind": "reference", "name": "Referência", "size": 2,
         "sha256": sha256(b"xx").hexdigest()},
    ]
    if tamper:
        items[0]["sha256"] = "0" * 64
    manifest = {"format": PACK_FORMAT, "assets": items}
    with ZipFile(path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr(background_path, bg)
        z.writestr("selos/quarta-cafe.png", seal)
        z.writestr("referencias/exemplo.jpg", b"xx")


def test_only_artwork_is_imported_and_archive_reimport_is_idempotent(tmp_path: Path):
    archive = tmp_path / "campaigns.zip"
    root = tmp_path / "library"
    make_pack(archive)
    stats = import_campaign_pack(archive.as_uri(), root=root)
    assert stats == {"imported": 2, "available": 2}
    files = list_campaign_assets(root=root)
    assert {item["kind"] for item in files} == {"background", "seal"}
    assert not any("referencias" in item["path"] for item in files)
    assert all(Path(item["path"]).is_file() for item in files)
    assert import_campaign_pack(archive, root=root)["available"] == 2


@pytest.mark.parametrize("unsafe", ["tamper", "traversal"])
def test_corrupt_or_unsafe_pack_never_mutates_existing_catalog(tmp_path: Path, unsafe):
    archive = tmp_path / "campaigns.zip"
    root = tmp_path / "library"
    make_pack(archive, **{unsafe: True})
    with pytest.raises(ValueError):
        import_campaign_pack(archive, root=root)
    assert list_campaign_assets(root=root) == []
    assert not (root / "catalog.json").exists()


def test_import_command_exposes_assets_for_qml_without_scene_product_changes(tmp_path: Path, monkeypatch):
    archive = tmp_path / "campaigns.zip"
    make_pack(archive)
    monkeypatch.setenv("SRSTUDIO_CAMPAIGN_ASSETS_DIR", str(tmp_path / "installed"))
    router = GraphicsCommandRouter(GraphicsSession(GraphicsDocument()))
    bundled = router.payload()["editor"]["campaign_assets"]
    assert len([entry for entry in bundled if entry.get("source") == "builtin"]) == 12
    result = router.dispatch({"name": "import_campaign_pack", "path": archive.as_uri()})
    assert result.ok, result.message
    assert not result.changed  # user library installation is not a document mutation
    catalog = router.payload()["editor"]["campaign_assets"]
    assert len(catalog) == len(bundled) + 2
    assert not router.session.page.slots
    chosen = next(item for item in catalog if item["kind"] == "background" and item["source"] == "user")
    applied = router.dispatch({
        "name": "set_campaign_art",
        "kind": "background", "campaign_id": "quarta-cafe",
        "path": chosen["path"]})
    assert applied.ok, applied.message
    assert applied.payload["node_id"] == router.session.page.metadata["campaign_background_node"]
