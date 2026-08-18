from __future__ import annotations

from hashlib import sha256
import json
import zipfile

import pytest

from srstudio.graphics2 import BindingRole, GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, Transform
from srstudio.graphics2.package import PACKAGE_FORMAT, load_package, save_package
from srstudio.graphics2.preflight import run_preflight


def test_scene_round_trip_preserves_semantics():
    document = GraphicsDocument(name="Teste")
    page = document.active_page
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        text="ARROZ 5KG",
        binding_role=BindingRole.NAME,
        transform=Transform(x=10, y=20, width=200, height=50),
    )
    page.add_node(node)
    restored = GraphicsDocument.from_dict(document.to_dict())
    clone = restored.active_page.nodes[node.id]
    assert clone.kind is NodeKind.TEXT
    assert clone.binding_role is BindingRole.NAME
    assert clone.transform.x == 10
    assert clone.text == "ARROZ 5KG"


def test_history_is_transactional_and_redoable():
    session = GraphicsSession()
    node = session.add_text("Produto", x=10, y=20, width=120, height=40)
    session.select(node.id)
    session.move_selected(30, 40)
    assert session.page.nodes[node.id].transform.x == 40
    assert session.undo()
    assert session.page.nodes[node.id].transform.x == 10
    assert session.redo()
    assert session.page.nodes[node.id].transform.x == 40


def test_product_binding_keeps_price_parts_separate():
    session = GraphicsSession()
    page = session.page
    fields = {}
    for role in (
        BindingRole.NAME,
        BindingRole.CURRENCY,
        BindingRole.PRICE_REAIS,
        BindingRole.PRICE_CENTS,
        BindingRole.UNIT,
        BindingRole.LIMIT,
    ):
        node = GraphicsNode(
            kind=NodeKind.TEXT,
            transform=Transform(width=100, height=30),
            binding_role=role,
        )
        page.add_node(node)
        fields[role] = node.id
    slot = session.create_slot("Produto 1", fields)
    session.bind_product(
        slot.id,
        {
            "id": "p1",
            "display_name": "ACÉM BOVINO",
            "price": "33,64",
            "unit": "KG",
            "cpf_limit": "6UN",
        },
    )
    assert page.nodes[fields[BindingRole.NAME]].text == "ACÉM BOVINO"
    assert page.nodes[fields[BindingRole.CURRENCY]].text == "R$"
    assert page.nodes[fields[BindingRole.PRICE_REAIS]].text == "33"
    assert page.nodes[fields[BindingRole.PRICE_CENTS]].text == ",64"
    assert page.nodes[fields[BindingRole.UNIT]].text == "/KG"
    assert page.nodes[fields[BindingRole.LIMIT]].text == "LIMITE DE 6UN POR CPF"


def test_preflight_detects_missing_asset_without_crashing():
    document = GraphicsDocument()
    page = document.active_page
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        asset_id="asset_missing",
        transform=Transform(x=0, y=0, width=100, height=100),
    )
    page.add_node(image)
    assert any(issue.code == "MISSING_ASSET" for issue in run_preflight(document))


def test_current_schema_package_roundtrip_accepts_exact_scene(tmp_path):
    document = GraphicsDocument(name="Round-trip exato")
    document.metadata["editor_state"] = {"zoom": 1.25, "panel": "layers"}
    document.active_page.guides_x = [100.5, 500.0]
    document.active_page.guides_y = [200.25]
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        text="OFERTA",
        transform=Transform(x=10.5, y=20.25, width=333.0, height=70.0, rotation=12.5),
        style={"font_family": "Arial", "font_size": 42, "fill": "#112233"},
        metadata={"editor_note": "preservar"},
    )
    document.active_page.add_node(node)

    path = save_package(document, tmp_path / "exact.srscene")
    restored = load_package(path)

    assert restored.to_dict() == document.to_dict()


def test_current_schema_package_rejects_unknown_property_instead_of_silent_drop(tmp_path):
    document = GraphicsDocument(name="Future field")
    scene = document.to_dict()
    scene["future_editor_state"] = {
        "selection": ["node_future"],
        "viewport": {"zoom": 1.5, "x": 22.0, "y": 14.0},
    }
    scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    manifest = {
        "format": PACKAGE_FORMAT,
        "schema": document.schema,
        "document_id": document.id,
        "assets": {},
        "fonts": [],
        "scene_sha256": sha256(scene_raw).hexdigest(),
    }
    path = tmp_path / "lossy.srscene"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("scene.json", scene_raw)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8"))

    with pytest.raises(ValueError, match="Round-trip canônico"):
        load_package(path)


def test_current_schema_package_allows_missing_optional_defaults_for_compatibility(tmp_path):
    document = GraphicsDocument(name="Older 2.0")
    scene = document.to_dict()
    scene.pop("metadata")
    page = scene["pages"][0]
    page.pop("metadata")
    page.pop("guides_x")
    page.pop("guides_y")
    scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    manifest = {
        "format": PACKAGE_FORMAT,
        "schema": document.schema,
        "document_id": document.id,
        "assets": {},
        "fonts": [],
        "scene_sha256": sha256(scene_raw).hexdigest(),
    }
    path = tmp_path / "older-current.srscene"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("scene.json", scene_raw)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8"))

    restored = load_package(path)

    assert restored.id == document.id
    assert restored.metadata == {}
    assert restored.active_page.guides_x == []
    assert restored.active_page.guides_y == []


def test_legacy_schema_alias_keeps_compatibility_normalization(tmp_path):
    document = GraphicsDocument(name="Legacy alias")
    scene = document.to_dict()
    scene["schema"] = "srscene/2"
    scene_raw = json.dumps(scene, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    manifest = {
        "format": PACKAGE_FORMAT,
        "schema": "srscene/2",
        "document_id": document.id,
        "assets": {},
        "fonts": [],
        "scene_sha256": sha256(scene_raw).hexdigest(),
    }
    path = tmp_path / "legacy.srscene"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("scene.json", scene_raw)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8"))

    restored = load_package(path)

    assert restored.schema == "srscene/2.0"
    assert restored.id == document.id
