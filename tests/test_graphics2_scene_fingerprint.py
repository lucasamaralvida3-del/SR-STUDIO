from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

from srstudio.graphics2.model import AssetRef, BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.scene_fingerprint import fingerprint_document, store_scene_fingerprint


def _scene(*, x: float = 10.0, asset_root: str = "C:/cache/a") -> GraphicsDocument:
    document = GraphicsDocument(name="Deterministic")
    asset = AssetRef(kind="image", source=f"{asset_root}/abcd1234.png", sha256="a" * 64)
    document.add_asset(asset)
    page = document.active_page
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem",
        transform=Transform(x=x, y=20, width=120, height=80),
        asset_id=asset.id,
        binding_role=BindingRole.IMAGE,
        style={"fit": "contain"},
    )
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        transform=Transform(x=10, y=110, width=200, height=40),
        text="ACÉM BOVINO",
        binding_role=BindingRole.NAME,
        style={"font_family": "Anton", "font_size": 24},
    )
    page.add_node(image)
    page.add_node(text)
    slot = SmartSlot(name="Produto 1", page_id=page.id, node_by_role={"image": image.id, "name": text.id})
    page.slots[slot.id] = slot
    return document


def test_fingerprint_survives_scene_round_trip_and_random_runtime_ids():
    first = _scene()
    second = _scene()
    round_trip = GraphicsDocument.from_dict(deepcopy(first.to_dict()))

    a = fingerprint_document(first)
    b = fingerprint_document(second)
    c = fingerprint_document(round_trip)

    assert a.sha256 == b.sha256 == c.sha256
    assert a.pages[0].sha256 == b.pages[0].sha256
    assert a.nodes == 2
    assert a.slots == 1


def test_fingerprint_changes_when_visual_geometry_changes():
    original = fingerprint_document(_scene(x=10.0))
    moved = fingerprint_document(_scene(x=10.25))
    assert original.sha256 != moved.sha256
    assert original.pages[0].sha256 != moved.pages[0].sha256


def test_asset_cache_directory_does_not_change_hash_when_content_hash_is_equal():
    first = fingerprint_document(_scene(asset_root="C:/users/a/cache"))
    second = fingerprint_document(_scene(asset_root="D:/temp/other-cache"))
    assert first.sha256 == second.sha256


def test_unhashed_local_asset_uses_content_identity_before_packaging(tmp_path):
    asset_path = tmp_path / "image.png"
    asset_path.write_bytes(b"same-image-content")

    document = _scene(asset_root=str(tmp_path))
    asset = next(iter(document.assets.values()))
    asset.source = str(asset_path)
    asset.sha256 = ""
    before = fingerprint_document(document)

    asset.sha256 = sha256(asset_path.read_bytes()).hexdigest()
    asset.source = "assets/image.png"
    after = fingerprint_document(document)

    assert before.sha256 == after.sha256
    assert before.pages[0].sha256 == after.pages[0].sha256


def test_store_scene_fingerprint_writes_serializable_metadata_without_self_affecting_hash():
    document = _scene()
    before = fingerprint_document(document)
    stored = store_scene_fingerprint(document)
    after = fingerprint_document(document)
    assert stored.sha256 == before.sha256 == after.sha256
    assert document.metadata["scene_fingerprint"]["sha256"] == before.sha256
