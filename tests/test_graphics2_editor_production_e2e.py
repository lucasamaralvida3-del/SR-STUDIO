from __future__ import annotations

from pathlib import Path

from srstudio.graphics2 import (
    GraphicsCommandRouter,
    GraphicsDocument,
    GraphicsNode,
    GraphicsSession,
    NodeKind,
    Transform,
)
from srstudio.graphics2 import qt_host
from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.editor_persistence import EditorRecoveryJournal, document_digest
from srstudio.graphics2.package import load_package, register_local_asset, save_package


def test_flow_1_new_project_objects_save_close_reopen(tmp_path):
    document = GraphicsDocument(name="Fluxo 1")
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)

    text = router.dispatch(
        {
            "name": "add_text",
            "text": "OFERTA DO DIA",
            "x": 100,
            "y": 150,
            "width": 420,
            "height": 90,
            "name_value": "Título",
        }
    )
    rect = router.dispatch(
        {
            "name": "add_rect",
            "x": 80,
            "y": 120,
            "width": 470,
            "height": 150,
            "fill": "#F2F2F2",
            "name_value": "Fundo",
        }
    )
    assert text.ok and rect.ok
    node_ids = set(document.active_page.nodes)

    target = save_package(document, tmp_path / "fluxo1.srscene", embed_local_assets=True)
    del session, router, document

    reopened = load_package(target)
    assert reopened.name == "Fluxo 1"
    assert set(reopened.active_page.nodes) == node_ids
    reopened_text = next(node for node in reopened.active_page.nodes.values() if node.name == "Título")
    assert reopened_text.text == "OFERTA DO DIA"


def test_flow_2_multipage_duplicate_page_is_independent():
    document = GraphicsDocument(name="Fluxo 2")
    session = GraphicsSession(document)
    first = document.active_page
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        text="ORIGINAL",
        transform=Transform(x=40, y=50, width=300, height=70),
    )
    first.add_node(node)
    first_page_id = first.id

    duplicate_id = session.add_page(name="Cópia", duplicate_active=True)
    duplicate = document.page(duplicate_id)
    assert duplicate is not None
    assert duplicate.id != first_page_id
    assert set(duplicate.nodes).isdisjoint(set(first.nodes))

    duplicate_text = next(item for item in duplicate.nodes.values() if item.name == "Nome")
    duplicate_text.text = "ALTERADO SOMENTE NA CÓPIA"

    assert first.nodes[node.id].text == "ORIGINAL"
    assert duplicate_text.text == "ALTERADO SOMENTE NA CÓPIA"


def test_flow_3_move_resize_rotate_undo_redo_roundtrip():
    document = GraphicsDocument(name="Fluxo 3")
    session = GraphicsSession(document)
    router = GraphicsCommandRouter(session)
    node = GraphicsNode(
        kind=NodeKind.RECT,
        name="Objeto",
        transform=Transform(x=100, y=100, width=200, height=120),
    )
    session.page.add_node(node)
    session.select(node.id)

    assert router.dispatch({"name": "move", "dx": 30, "dy": 40, "snap": False}).changed
    assert router.dispatch({"name": "resize", "node_id": node.id, "width": 260, "height": 150}).changed
    assert router.dispatch({"name": "rotate", "angle": 25}).changed

    edited = session.page.nodes[node.id].transform
    assert (edited.x, edited.y, edited.width, edited.height, edited.rotation) == (130, 140, 260, 150, 25)

    for _ in range(3):
        assert router.dispatch({"name": "undo"}).changed
    restored = session.page.nodes[node.id].transform
    assert (restored.x, restored.y, restored.width, restored.height, restored.rotation) == (100, 100, 200, 120, 0)

    for _ in range(3):
        assert router.dispatch({"name": "redo"}).changed
    redone = session.page.nodes[node.id].transform
    assert (redone.x, redone.y, redone.width, redone.height, redone.rotation) == (130, 140, 260, 150, 25)


def test_flow_4_autosave_and_recovery_after_unsaved_change(tmp_path, monkeypatch):
    autosave_root = tmp_path / "autosave"
    monkeypatch.setattr(qt_host, "default_autosave_root", lambda: autosave_root)
    manager = AutosaveManager(autosave_root)
    journal = EditorRecoveryJournal(autosave_root)

    saved = GraphicsDocument(name="Fluxo 4")
    saved.metadata["revision"] = 1
    project = save_package(saved, tmp_path / "fluxo4.srscene", embed_local_assets=True)
    base_digest = document_digest(saved)

    pending = GraphicsDocument.from_dict(saved.to_dict())
    pending.metadata["revision"] = 2
    recovery_path = manager.save(pending)
    journal.mark(
        pending.id,
        recovery_path,
        source_path=project,
        base_saved_digest=base_digest,
    )

    context = qt_host.load_launch_context(project)

    assert context.recovered_from is not None
    assert context.source == project.resolve()
    assert context.saved_digest == base_digest
    assert context.document.id == saved.id
    assert context.document.metadata["revision"] == 2
    assert document_digest(context.document) != context.saved_digest


def test_flow_5_text_and_image_survive_save_load_without_original_asset(tmp_path):
    image_path = tmp_path / "produto.png"
    raw = b"editor-flow-image"
    image_path.write_bytes(raw)

    document = GraphicsDocument(name="Fluxo 5")
    asset = register_local_asset(document, image_path, kind="image", mime="image/png")
    text = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Produto nome",
        text="ARROZ TESTE 5KG",
        transform=Transform(x=80, y=800, width=500, height=100),
        style={"font_family": "Arial", "font_size": 40.0, "font_weight": 700},
    )
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Produto imagem",
        asset_id=asset.id,
        transform=Transform(x=130, y=180, width=420, height=520),
        style={"fit": "cover", "focus_x": 0.4, "focus_y": 0.6, "zoom": 1.2},
    )
    document.active_page.add_node(text)
    document.active_page.add_node(image)

    target = save_package(document, tmp_path / "fluxo5.srscene", embed_local_assets=True)
    image_path.unlink()
    reopened = load_package(target, extract_assets_to=tmp_path / "assets")

    reopened_text = reopened.active_page.nodes[text.id]
    reopened_image = reopened.active_page.nodes[image.id]
    assert reopened_text.text == "ARROZ TESTE 5KG"
    assert reopened_text.style["font_family"] == "Arial"
    assert reopened_image.asset_id == asset.id
    assert reopened_image.style["fit"] == "cover"
    extracted = Path(reopened.assets[asset.id].source)
    assert extracted.is_file()
    assert extracted.read_bytes() == raw


def test_flow_6_export_is_reachable_from_editor_ui():
    qml = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "srstudio"
        / "graphics2"
        / "qml"
        / "ProjectActions.qml"
    ).read_text(encoding="utf-8")

    assert "sceneBridge.exportPdf(selectedFile.toString())" in qml
    assert "sceneBridge.exportPng(selectedFile.toString())" in qml
    assert 'text: "PDF"' in qml
    assert 'text: "PNG"' in qml
