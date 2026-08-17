from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

from srstudio.graphics2 import GraphicsCommandRouter, GraphicsSession, NodeKind, smart_slot_bounds
from srstudio.graphics2.autosave import AutosaveManager
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.qt_host import load_launch_context
from srstudio.graphics2.qt_renderer import render_pdf, render_png
from srstudio.graphics2.usability_gate import inspect_encarte_usability


_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_TEMPLATE = (
    _REPO_ROOT
    / "src"
    / "srstudio"
    / "assets"
    / "poster_templates"
    / "legacy"
    / "models"
    / "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"
)


def _node_by_name(page, name: str):
    return next(node for node in page.nodes.values() if node.name == name)


def _assert_same_pixels(left: Path, right: Path) -> None:
    with Image.open(left) as left_image, Image.open(right) as right_image:
        a = left_image.convert("RGBA")
        b = right_image.convert("RGBA")
        assert a.size == b.size
        assert ImageChops.difference(a, b).getbbox() is None


def test_real_preview_end_to_end_operator_flow(tmp_path: Path):
    """Single-session Professional Usable gate using a real SR PPTX.

    This deliberately follows the operator path instead of calling individual
    low-level helpers: import, drop product, edit/move/resize, replace an image,
    undo/redo, duplicate page, autosave/recover, save/open, PNG and PDF.
    """

    assert _REAL_TEMPLATE.is_file()
    context = load_launch_context(_REAL_TEMPLATE)
    session = GraphicsSession(context.document)
    router = GraphicsCommandRouter(session)
    page = session.page

    assert len(page.slots) == 1
    slot = next(iter(page.slots.values()))
    bounds = smart_slot_bounds(page, slot)
    assert bounds is not None

    # 1) O mesmo comando do drag-and-drop da UI precisa preencher o card real.
    product = {
        "id": "preview-e2e-001",
        "name": "ARROZ PREVIEW 5KG",
        "price": "24.90",
        "app_price": "22.49",
        "unit": "UN",
        "cpf_limit": "6UN",
    }
    drop = router.dispatch(
        {
            "name": "drop_product",
            "x": bounds.center_x,
            "y": bounds.center_y,
            "product": product,
            "magnet_distance": 0,
        }
    )
    assert drop.ok is True and drop.changed is True, drop.to_dict()
    assert next(iter(session.page.slots.values())).product_id == product["id"]
    assert _node_by_name(session.page, "SR_PRODUTO").text == "ARROZ PREVIEW 5KG"
    assert _node_by_name(session.page, "SR_PRECO_PROMO").text == "24,90"
    assert _node_by_name(session.page, "SR_PRECO_CLUBE").text == "22,49"
    assert _node_by_name(session.page, "SR_LIMITE").text == "LIMITE DE 6UN POR CPF"

    # 2) Edição textual explícita pelo Command Router usado pela interface.
    name_node = _node_by_name(session.page, "SR_PRODUTO")
    edit = router.dispatch({"name": "edit_text", "node_id": name_node.id, "text": "ARROZ PREVIEW EDITADO 5KG"})
    assert edit.ok is True and edit.changed is True
    assert session.page.node(name_node.id).text == "ARROZ PREVIEW EDITADO 5KG"

    # 3) Seleção, movimento e resize reais, com undo/redo da última operação.
    select = router.dispatch({"name": "select", "node_id": name_node.id})
    assert select.ok is True
    old_x = session.page.node(name_node.id).transform.x
    old_width = session.page.node(name_node.id).transform.width
    old_height = session.page.node(name_node.id).transform.height
    moved = router.dispatch({"name": "move", "dx": 14, "dy": 6, "snap": False})
    assert moved.ok is True and moved.changed is True
    assert session.page.node(name_node.id).transform.x == old_x + 14
    resized = router.dispatch(
        {
            "name": "resize",
            "node_id": name_node.id,
            "width": old_width + 36,
            "height": old_height + 12,
        }
    )
    assert resized.ok is True and resized.changed is True
    assert session.page.node(name_node.id).transform.width == old_width + 36
    assert router.dispatch({"name": "undo"}).changed is True
    assert session.page.node(name_node.id).transform.width == old_width
    assert router.dispatch({"name": "redo"}).changed is True
    assert session.page.node(name_node.id).transform.width == old_width + 36

    # 4) Substituição de uma imagem importada preserva o frame e entra no history.
    image_node = next(
        node
        for node in session.page.nodes.values()
        if node.kind is NodeKind.IMAGE and node.visible and not session.effective_locked(node.id)
    )
    replacement = tmp_path / "replacement.png"
    Image.new("RGBA", (96, 72), (230, 240, 250, 255)).save(replacement)
    original_asset_id = image_node.asset_id
    original_frame = (
        image_node.transform.x,
        image_node.transform.y,
        image_node.transform.width,
        image_node.transform.height,
    )
    replaced = router.dispatch({"name": "replace_image", "node_id": image_node.id, "source": str(replacement)})
    assert replaced.ok is True and replaced.changed is True, replaced.to_dict()
    assert session.page.node(image_node.id).asset_id != original_asset_id
    assert (
        session.page.node(image_node.id).transform.x,
        session.page.node(image_node.id).transform.y,
        session.page.node(image_node.id).transform.width,
        session.page.node(image_node.id).transform.height,
    ) == original_frame
    replacement_asset_id = session.page.node(image_node.id).asset_id
    assert router.dispatch({"name": "undo"}).changed is True
    assert session.page.node(image_node.id).asset_id == original_asset_id
    assert router.dispatch({"name": "redo"}).changed is True
    assert session.page.node(image_node.id).asset_id == replacement_asset_id

    # 5) Render antes do round-trip para provar coerência visual de persistência.
    before_png = tmp_path / "before-roundtrip.png"
    before_report = render_png(session.document, before_png, page_index=0, dpi=96)
    assert before_report.ok is True

    # 6) Duplicação multipágina precisa manter produto e identidades seguras.
    duplicate = router.dispatch({"name": "duplicate_page", "name_value": "Página 2"})
    assert duplicate.ok is True and duplicate.changed is True
    assert len(session.document.pages) == 2
    duplicated_page_id = session.document.active_page_id
    assert duplicated_page_id == duplicate.payload["page_id"]
    duplicate_slot = next(iter(session.page.slots.values()))
    assert duplicate_slot.product_id == product["id"]

    gate = inspect_encarte_usability(session.document, require_semantic_products=True, require_bound_product=True)
    assert gate.ready is True, gate.to_dict()
    assert gate.metrics["duplicate_page_ids"] == 0
    assert gate.metrics["duplicate_node_ids"] == 0
    assert gate.metrics["duplicate_slot_ids"] == 0

    # 7) Autosave precisa recuperar exatamente a sessão multipágina atual.
    autosave = AutosaveManager(tmp_path / "autosave", generations=3)
    autosave_path = autosave.save(session.document)
    assert autosave_path.is_file()
    point = autosave.latest(session.document.id)
    assert point is not None
    recovered = autosave.recover(point, extract_assets_to=tmp_path / "autosave-assets")
    assert recovered.id == session.document.id
    assert recovered.active_page_id == duplicated_page_id
    assert len(recovered.pages) == 2
    assert next(iter(recovered.active_page.slots.values())).product_id == product["id"]

    # 8) Save/close/reopen real com assets embutidos.
    scene_path = tmp_path / "professional-usable-preview.srscene"
    save_package(session.document, scene_path, embed_local_assets=True)
    restored = load_package(scene_path, extract_assets_to=tmp_path / "restored-assets")
    restored_gate = inspect_encarte_usability(restored, require_semantic_products=True, require_bound_product=True)
    assert restored_gate.ready is True, restored_gate.to_dict()
    assert restored.active_page_id == duplicated_page_id
    assert len(restored.pages) == 2
    assert _node_by_name(restored.pages[0], "SR_PRODUTO").text == "ARROZ PREVIEW EDITADO 5KG"
    assert _node_by_name(restored.pages[0], "SR_PRECO_PROMO").text == "24,90"
    assert _node_by_name(restored.pages[0], "SR_PRECO_CLUBE").text == "22,49"
    assert _node_by_name(restored.pages[0], "SR_LIMITE").text == "LIMITE DE 6UN POR CPF"

    # 9) PNG antes/depois do round-trip deve ser pixel-idêntico na página 1.
    after_png = tmp_path / "after-roundtrip.png"
    after_report = render_png(restored, after_png, page_index=0, dpi=96)
    assert after_report.ok is True
    _assert_same_pixels(before_png, after_png)

    # 10) PDF final precisa conter as duas páginas; PNG da página ativa também.
    active_png = tmp_path / "active-page.png"
    active_index = next(index for index, item in enumerate(restored.pages) if item.id == restored.active_page_id)
    assert render_png(restored, active_png, page_index=active_index, dpi=96).ok is True
    pdf_path = tmp_path / "professional-usable-preview.pdf"
    pdf_report = render_pdf(restored, pdf_path, dpi=144)
    assert pdf_report.ok is True
    assert pdf_report.pages == 2
    assert active_png.is_file() and active_png.stat().st_size > 0
    assert pdf_path.is_file() and pdf_path.stat().st_size > 0
