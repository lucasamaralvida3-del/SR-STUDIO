from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import zipfile

import pytest
from PIL import Image

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.image_database_runtime import (
    GraphicsImageDatabaseRuntime,
    ImageDatabaseIntegrityError,
    SEED_SCHEMA,
)
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.images.safe_library import SafeImageLibrary


def _png(path: Path, value: int = 80) -> Path:
    Image.new("RGBA", (72, 96), (value, 120, 180, 255)).save(path)
    return path


def _provenance(name: str) -> dict:
    return {
        "provenance": [{"source_file": "approved-corpus.pptx", "slide_index": 1, "product": name}],
        "source_provenance": [{"source": "canva", "source_file": "approved-corpus.pptx"}],
    }


def _asset(library: SafeImageLibrary, source: Path, name: str, *, aliases=(), accepted=True, confidence=0.96):
    return library.import_image(
        source,
        product_key=name,
        product_name=name,
        aliases=tuple(aliases),
        kind="product",
        confidence=confidence,
        review_status="accepted" if accepted else "pending",
        source_kind="canva",
        source_file="approved-corpus.pptx",
        metadata=_provenance(name),
    )


def _runtime(tmp_path: Path, rows=None):
    data_dir = tmp_path / "user-data"
    library = SafeImageLibrary(data_dir / "images")
    assets = []
    for index, (name, aliases, accepted) in enumerate(rows or []):
        assets.append(_asset(library, _png(tmp_path / f"asset-{index}.png", 40 + index * 20), name, aliases=aliases, accepted=accepted))
    runtime = GraphicsImageDatabaseRuntime(data_dir)
    assert runtime.available, runtime.error
    return runtime, library, assets


def _document(product_name: str = "BATATA INGLESA"):
    document = GraphicsDocument()
    page = document.active_page
    image = GraphicsNode(
        id="image-node",
        kind=NodeKind.IMAGE,
        name="Imagem Produto",
        transform=Transform(x=100, y=200, width=260, height=320),
        visible=False,
        metadata={
            "crop": {"left": 0.05, "top": 0.1, "right": 0.02, "bottom": 0.03},
            "clip_path": {"kind": "ellipse", "points": [[0, 0], [1, 1]]},
            "placeholder_geometry": {"x": 100, "y": 200, "width": 260, "height": 320},
        },
    )
    name = GraphicsNode(id="name-node", kind=NodeKind.TEXT, name="Nome", transform=Transform(x=90, y=540, width=300, height=70))
    page.add_node(image)
    page.add_node(name)
    slot = SmartSlot(
        id="slot-1",
        page_id=page.id,
        node_by_role={BindingRole.IMAGE.value: image.id, BindingRole.NAME.value: name.id},
    )
    page.slots[slot.id] = slot
    document.metadata["products"] = [
        {"id": "product-1", "name": product_name, "display_name": product_name, "unit": "UN", "price": 9.99},
        {"id": "product-2", "name": "OUTRO PRODUTO", "display_name": "OUTRO PRODUTO", "unit": "UN", "price": 4.99},
    ]
    return document, slot, image


def _attach(runtime, document):
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    runtime.attach(session, router)
    return session, router


def test_known_product_uses_existing_lookup_and_correct_image(tmp_path: Path) -> None:
    runtime, _, assets = _runtime(tmp_path, [("BATATA INGLESA", (), True)])
    result = runtime.lookup_product("BATATA INGLESA")
    assert result.best_match is not None
    assert result.best_match.asset.id == assets[0].id
    assert result.confidence >= 0.67


def test_alias_resolves_same_existing_image_id(tmp_path: Path) -> None:
    runtime, _, assets = _runtime(tmp_path, [("TOMATE PERA", ("TOMATE PÊRA", "TOMATE PERA KG"), True)])
    direct = runtime.lookup_product("TOMATE PERA")
    alias = runtime.lookup_product("TOMATE PÊRA")
    assert direct.best_match is not None and alias.best_match is not None
    assert direct.best_match.asset.id == alias.best_match.asset.id == assets[0].id


def test_unknown_product_never_auto_applies_wrong_image(tmp_path: Path) -> None:
    runtime, _, _ = _runtime(tmp_path, [("BATATA INGLESA", (), True)])
    assert runtime.lookup_product("SHAMPOO MARCA INEXISTENTE 900ML").best_match is None
    document, slot, image = _document("SHAMPOO MARCA INEXISTENTE 900ML")
    session, _ = _attach(runtime, document)
    before = deepcopy(image.transform)
    session.bind_product(slot.id, document.metadata["products"][0])
    assert image.asset_id == ""
    assert "bound_image_source" not in image.metadata
    assert image.visible is False
    assert image.transform == before
    assert slot.metadata["image_db_lookup"]["status"] == "not-found"


def test_confident_product_bind_applies_image_without_touching_geometry(tmp_path: Path) -> None:
    runtime, _, assets = _runtime(tmp_path, [("BATATA INGLESA", (), True)])
    document, slot, image = _document()
    session, _ = _attach(runtime, document)
    transform_before = deepcopy(image.transform)
    crop_before = deepcopy(image.metadata["crop"])
    clip_before = deepcopy(image.metadata["clip_path"])
    session.bind_product(slot.id, document.metadata["products"][0])
    assert image.visible is True
    assert image.transform == transform_before
    assert image.metadata["crop"] == crop_before
    assert image.metadata["clip_path"] == clip_before
    assert Path(image.metadata["bound_image_source"]).resolve() == Path(assets[0].path).resolve()
    assert slot.metadata["product_snapshot"]["image_db_image_id"] == assets[0].id
    assert slot.metadata["image_db_lookup"]["status"] == "auto-applied"


def test_manual_choice_persists_association_and_save_reopen_binding(tmp_path: Path) -> None:
    runtime, library, assets = _runtime(tmp_path, [("BATATA INGLESA", (), True), ("BATATA ESPECIAL", (), False)])
    document, slot, image = _document()
    _, router = _attach(runtime, document)
    transform_before = deepcopy(image.transform)
    selected = assets[1]
    result = router.dispatch({"name": "apply_product_image", "slot_id": slot.id, "product_id": "product-1", "image_id": selected.id})
    assert result.ok and result.changed
    assert image.transform == transform_before
    assert slot.metadata["product_snapshot"]["image_db_image_id"] == selected.id

    saved = save_package(document, tmp_path / "manual-image.srscene", embed_local_assets=True)
    reopened = load_package(saved, extract_assets_to=tmp_path / "reopened-assets")
    reopened_slot = reopened.active_page.slots[slot.id]
    reopened_image = reopened.active_page.node(image.id)
    assert reopened_image is not None and reopened_image.visible
    assert reopened_image.asset_id
    assert reopened_slot.metadata["product_snapshot"]["image_db_image_id"] == selected.id

    updated = next(asset for asset in library.all() if asset.id == selected.id)
    rows = updated.metadata.get("manual_associations")
    assert isinstance(rows, list) and rows
    row = rows[-1]
    assert row["product_normalized_name"] == "BATATA INGLESA"
    assert row["selected_image_id"] == selected.id
    assert row["manual_confirmation"] is True
    assert row["confidence"] == 1.0
    assert "BATATA INGLESA" in updated.aliases
    assert updated.review_status == "accepted"


def test_replacing_one_slot_does_not_change_other_slot(tmp_path: Path) -> None:
    runtime, _, assets = _runtime(tmp_path, [("BATATA INGLESA", (), True), ("TOMATE PERA", (), True)])
    document, slot1, _ = _document()
    page = document.active_page
    image2 = GraphicsNode(id="image-node-2", kind=NodeKind.IMAGE, transform=Transform(x=500, y=200, width=260, height=320), metadata={"crop": {"left": 0.1}})
    page.add_node(image2)
    slot2 = SmartSlot(id="slot-2", page_id=page.id, node_by_role={BindingRole.IMAGE.value: image2.id})
    page.slots[slot2.id] = slot2
    session, router = _attach(runtime, document)
    session.bind_product(slot2.id, {"id": "p-tomate", "name": "TOMATE PERA"})
    other_before = (image2.asset_id, deepcopy(image2.transform), deepcopy(image2.metadata), deepcopy(slot2.metadata))
    result = router.dispatch({"name": "apply_product_image", "slot_id": slot1.id, "product_id": "product-1", "image_id": assets[0].id})
    assert result.ok
    assert (image2.asset_id, image2.transform, image2.metadata, slot2.metadata) == other_before


def _seed_from_library(tmp_path: Path, library: SafeImageLibrary, *, total_products: int = 520) -> Path:
    payload = library._load()
    relative = {}
    for asset_id, raw in payload.items():
        row = deepcopy(raw)
        row["path"] = f"assets/{Path(row['path']).name}"
        relative[asset_id] = row
    canonical = json.dumps(relative, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    manifest = {
        "schema": SEED_SCHEMA,
        "catalog_version": "test-catalog-v1",
        "total_products": total_products,
        "total_images": len(relative),
        "index_sha256": sha256(canonical).hexdigest(),
        "source_release": "image-db-corpus-v1",
        "source_artifact": "test-approved-index",
        "provenance_status": "PASS",
        "dedup_status": "PASS",
    }
    seed = tmp_path / "image-db-library-v1.zip"
    with zipfile.ZipFile(seed, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.json", json.dumps(relative, ensure_ascii=False, indent=2))
        archive.writestr("seed-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for asset_id, row in relative.items():
            archive.write(Path(payload[asset_id]["path"]), f"assets/{Path(row['path']).name}")
    return seed


def test_seed_bootstraps_same_official_root_not_parallel_catalog(tmp_path: Path) -> None:
    source_library = SafeImageLibrary(tmp_path / "builder" / "images")
    asset = _asset(source_library, _png(tmp_path / "known.png"), "BATATA INGLESA")
    seed = _seed_from_library(tmp_path, source_library)
    data_dir = tmp_path / "clean-user-data"
    (data_dir / "images" / "assets").mkdir(parents=True)
    runtime = GraphicsImageDatabaseRuntime(data_dir, seed_path=seed, require_library=True)
    assert runtime.available
    assert runtime.library_root == data_dir.resolve() / "images"
    assert runtime.library is not None and runtime.library.root == data_dir.resolve() / "images"
    result = runtime.lookup_product("BATATA INGLESA")
    assert result.best_match is not None and result.best_match.asset.id == asset.id
    assert Path(result.best_match.asset.path).resolve().is_relative_to((data_dir / "images" / "assets").resolve())
    assert not (data_dir / "image-db-beta").exists()
    assert not (data_dir / "graphics2-images").exists()


def test_seed_manifest_is_reloaded_and_revalidated_after_runtime_reopen(tmp_path: Path) -> None:
    source_library = SafeImageLibrary(tmp_path / "builder-reopen" / "images")
    asset = _asset(source_library, _png(tmp_path / "known-reopen.png"), "BATATA INGLESA")
    seed = _seed_from_library(tmp_path, source_library, total_products=520)
    data_dir = tmp_path / "reopen-user-data"
    first = GraphicsImageDatabaseRuntime(data_dir, seed_path=seed, require_library=True)
    assert first.seed_manifest["total_products"] == 520
    assert first.seed_manifest["total_images"] == 1
    assert first.seed_manifest["provenance_status"] == "PASS"
    assert first.seed_manifest["dedup_status"] == "PASS"

    second = GraphicsImageDatabaseRuntime(data_dir, require_library=True)
    assert second.available
    assert second.seed_manifest == first.seed_manifest
    result = second.lookup_product("BATATA INGLESA")
    assert result.best_match is not None and result.best_match.asset.id == asset.id

    persisted_manifest = data_dir / "images" / "seed-manifest.json"
    tampered = json.loads(persisted_manifest.read_text(encoding="utf-8"))
    tampered["provenance_status"] = "UNKNOWN"
    persisted_manifest.write_text(json.dumps(tampered), encoding="utf-8")
    invalid = GraphicsImageDatabaseRuntime(data_dir)
    assert not invalid.available
    assert "provenance" in invalid.error.lower()
    with pytest.raises(ImageDatabaseIntegrityError):
        GraphicsImageDatabaseRuntime(data_dir, require_library=True)


@pytest.mark.parametrize("mutation, expected", [
    ("missing_provenance", "Provenance ausente"),
    ("missing_hash", "sha256_full"),
    ("missing_file", "Arquivo referenciado ausente"),
    ("bad_image_id", "image_id"),
])
def test_integrity_fail_closed(tmp_path: Path, mutation: str, expected: str) -> None:
    data_dir = tmp_path / mutation
    library = SafeImageLibrary(data_dir / "images")
    asset = _asset(library, _png(tmp_path / f"{mutation}.png"), "BATATA INGLESA")
    payload = library._load()
    raw = payload[asset.id]
    if mutation == "missing_provenance":
        raw["metadata"].pop("provenance", None)
        raw["metadata"].pop("source_provenance", None)
    elif mutation == "missing_hash":
        raw["metadata"].pop("sha256_full", None)
    elif mutation == "missing_file":
        Path(raw["path"]).unlink()
    elif mutation == "bad_image_id":
        raw["id"] = "different"
    library.index_path.write_text(json.dumps(payload), encoding="utf-8")
    runtime = GraphicsImageDatabaseRuntime(data_dir)
    assert not runtime.available
    assert expected.lower() in runtime.error.lower()
    with pytest.raises(Exception):
        GraphicsImageDatabaseRuntime(data_dir, require_library=True)


def test_payload_preview_is_suggestion_only_and_does_not_fill_slots(tmp_path: Path) -> None:
    runtime, _, assets = _runtime(tmp_path, [("BATATA INGLESA", (), True)])
    document, slot, image = _document()
    _, router = _attach(runtime, document)
    payload = router.payload()
    runtime.augment_payload(payload)
    product = payload["editor"]["products"][0]
    assert product["image_db_found"] is True
    assert product["image_db_preview"] == assets[0].path
    assert product["image_db_candidates"]
    assert slot.product_id == ""
    assert slot.metadata.get("product_snapshot") in (None, {})
    assert image.asset_id == ""
    assert image.visible is False


def test_ambiguous_existing_matches_require_manual_choice(tmp_path: Path) -> None:
    runtime, _, assets = _runtime(tmp_path, [("BATATA INGLESA", (), True), ("BATATA INGLESA", (), True)])
    candidates = runtime.product_candidates({"id": "p", "name": "BATATA INGLESA"})
    assert len(candidates) >= 2
    assert {row["image_id"] for row in candidates[:2]} == {assets[0].id, assets[1].id}
    assert not any(row["automatic"] for row in candidates)
    document, slot, image = _document("BATATA INGLESA")
    session, _ = _attach(runtime, document)
    transform_before = deepcopy(image.transform)
    session.bind_product(slot.id, document.metadata["products"][0])
    assert image.asset_id == ""
    assert image.visible is False
    assert image.transform == transform_before
    assert slot.metadata["image_db_lookup"]["status"] == "candidates"
    assert len(slot.metadata["image_db_lookup"]["candidate_ids"]) >= 2
