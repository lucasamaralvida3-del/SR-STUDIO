from __future__ import annotations

from pathlib import Path

from PIL import Image

from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.product_image_library import (
    store_product_image, read_product_links, apply_stored_product_links, attach_image_to_document,
)


def test_product_picture_survives_source_deletion_and_project_restart(tmp_path):
    root = tmp_path / "SRStudio" / "ProductImages"
    original = tmp_path / "source.png"
    Image.new("RGBA", (40, 30), (10, 130, 70, 210)).save(original)
    entry = store_product_image("07021", "MOELA DE FRANGO", str(original), root=root)
    assert Path(entry["image_path"]).is_file()
    original.unlink()
    reopened = GraphicsDocument.from_dict(GraphicsDocument().to_dict())
    reopened.metadata["products"] = [
        {"id": "07021", "name": "MOELA DE FRANGO", "price": "14.68"},
        {"id": "07022", "name": "MOELA DE FRANGO PREMIUM", "price": "16.50"},
    ]
    assert apply_stored_product_links(reopened, root=root) == 1
    assert reopened.metadata["products"][0]["image_path"] == entry["image_path"]
    assert "image_path" not in reopened.metadata["products"][1]
    assert read_product_links(root=root)["07021"]["name"] == "MOELA DE FRANGO"


def test_product_link_updates_existing_catalog_and_overwrites_only_same_id(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (24, 24), "red").save(a)
    Image.new("RGB", (24, 24), "blue").save(b)
    root = tmp_path / "library"
    first = store_product_image("120", "CAFÉ", str(a), root=root)
    second = store_product_image("120", "CAFÉ", str(b), root=root)
    assert first["sha256"] != second["sha256"]
    document = GraphicsDocument()
    document.metadata["products"] = [{"id": "120", "name": "CAFÉ"}, {"id": "121", "name": "CAFÉ"}]
    assert attach_image_to_document(document, "120", second)
    assert document.metadata["products"][0]["image_path"] == second["image_path"]
    assert "image_path" not in document.metadata["products"][1]


def test_image_import_validates_file_before_persisting(tmp_path):
    from pytest import raises
    source = tmp_path / "fake.png"
    source.write_text("not an image", encoding="utf-8")
    with raises(Exception):
        store_product_image("222", "TESTE", str(source), root=tmp_path / "library")
    assert not (tmp_path / "library" / "products.json").exists()


def test_qml_right_click_and_minimal_inspector():
    qml = (Path(__file__).resolve().parents[1] /
           "src/srstudio/graphics2/qml/GraphicsEditor.qml").read_text(encoding="utf-8")
    assert "acceptedButtons: Qt.LeftButton | Qt.RightButton" in qml
    assert 'text: "Adicionar ou substituir imagem"' in qml
    assert "sceneBridge.attachProductImage(" in qml
    for removed in ['text: "Aplicar geometria"', 'text: "Opacidade"',
                    'text: "Organizar"', 'text: "Qt Quick / RHI']:
        assert removed not in qml
    assert 'Label { id: inspectorName;' in qml
    assert "id: textEditor" in qml
