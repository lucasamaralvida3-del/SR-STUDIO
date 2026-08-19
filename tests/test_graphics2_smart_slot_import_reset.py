from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2 import full_studio_bridge, import_bridge
from srstudio.graphics2.import_bridge import CanvaBindingService, GraphicsImportService
from srstudio.graphics2.model import (
    AssetRef,
    BindingRole,
    GraphicsDocument,
    GraphicsNode,
    GraphicsPage,
    NodeKind,
    SmartSlot,
    Transform,
)
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import save_package
from srstudio.graphics2.qt_host import load_launch_context
from srstudio.graphics2.smart_slot_import_reset import reset_new_pptx_import_product_content


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "src" / "srstudio" / "assets" / "poster_templates" / "legacy" / "models"
IMPORT_A = MODELS / "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx"
IMPORT_B = MODELS / "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"


class _FakeProcess:
    pid = 9191


def _node(
    node_id: str,
    kind: NodeKind,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    text: str = "",
    asset_id: str = "",
    metadata: dict | None = None,
) -> GraphicsNode:
    return GraphicsNode(
        id=node_id,
        kind=kind,
        name=node_id,
        transform=Transform(x=x, y=y, width=width, height=height),
        text=text,
        asset_id=asset_id,
        metadata=dict(metadata or {}),
    )


def _logical_reset_fixture() -> tuple[GraphicsDocument, StudioProject, SmartSlot]:
    product = Product(
        id="product-old",
        original_name="PRODUTO ORIGINAL",
        display_name="PRODUTO ORIGINAL",
        price="9.99",
        retail_price="9.99",
        wholesale_price="8.49",
        quantity="3",
        unit="UN",
        image_path="C:/original.png",
        source="pptx",
    )
    card = ProductCard(
        id="slot-structural",
        product_id=product.id,
        x=100,
        y=200,
        width=280,
        height=340,
        overrides={
            "slot_template_product_id": product.id,
            "slot_filled": False,
            "recognition_confidence": 0.98,
        },
    )
    legacy = StudioProject(
        id="legacy-project",
        name="Import novo",
        products=[product],
        pages=[Page(id="page-1", cards=[card])],
    )

    page = GraphicsPage(id="page-1", width=1080, height=1350)
    document = GraphicsDocument(id="doc-reset", pages=[page], active_page_id=page.id)
    document.assets["asset-original"] = AssetRef(
        id="asset-original",
        kind="image",
        source="C:/original.png",
    )

    nodes = [
        _node("name", NodeKind.TEXT, 120, 220, 200, 42, text="PRODUTO ORIGINAL"),
        _node("image", NodeKind.IMAGE, 130, 280, 160, 150, asset_id="asset-original", metadata={
            "bound_image_source": "C:/original.png",
            "template_path": "C:/original.png",
            "template_hidden": False,
        }),
        _node("currency", NodeKind.TEXT, 140, 450, 32, 28, text="R$"),
        _node("reais", NodeKind.TEXT, 175, 440, 70, 44, text="9"),
        _node("cents", NodeKind.TEXT, 245, 445, 45, 30, text=",99"),
        _node("unit", NodeKind.TEXT, 250, 477, 50, 24, text="/UN"),
        _node("quantity", NodeKind.TEXT, 120, 510, 80, 26, text="3 UN"),
        _node("retail", NodeKind.TEXT, 210, 510, 80, 26, text="9,99"),
        _node("wholesale", NodeKind.TEXT, 300, 510, 80, 26, text="8,49"),
    ]
    for node in nodes:
        page.add_node(node)

    slot = SmartSlot(
        id="slot-structural",
        name="Produto 1",
        page_id=page.id,
        product_id=product.id,
        node_by_role={
            BindingRole.NAME.value: "name",
            BindingRole.IMAGE.value: "image",
            BindingRole.CURRENCY.value: "currency",
            BindingRole.PRICE_REAIS.value: "reais",
            BindingRole.PRICE_CENTS.value: "cents",
            BindingRole.UNIT.value: "unit",
            BindingRole.QUANTITY.value: "quantity",
            BindingRole.RETAIL_PRICE.value: "retail",
            BindingRole.WHOLESALE_PRICE.value: "wholesale",
        },
        metadata={
            "product_snapshot": product.to_dict(),
            "extra_bindings": {"price_complete": ["reais", "cents"]},
            "effective_bounds": {"x": 100.0, "y": 200.0, "width": 280.0, "height": 340.0},
            "display_index": 1,
            "semantic_product_card_id": "card-1",
            "bound_product_id": product.id,
            "bound_quantity": "3",
            "bound_retail_price": "9.99",
            "bound_wholesale_price": "8.49",
        },
    )
    page.slots[slot.id] = slot
    document.metadata["products"] = [product.to_dict()]
    return document, legacy, slot


def test_new_import_reset_preserves_slot_structure_and_original_visuals() -> None:
    document, legacy, slot = _logical_reset_fixture()
    page = document.active_page
    before_roles = dict(slot.node_by_role)
    before_extras = dict(slot.metadata["extra_bindings"])
    before_bounds = dict(slot.metadata["effective_bounds"])
    before_visual = {
        node.id: (
            node.transform.x,
            node.transform.y,
            node.transform.width,
            node.transform.height,
            node.text,
            node.asset_id,
            node.visible,
        )
        for node in page.nodes.values()
    }

    report = reset_new_pptx_import_product_content(document, legacy, source="novo.pptx")

    assert report.slots_reset == 1
    assert report.source_text_mutations == 0
    assert report.source_geometry_mutations == 0
    assert report.source_nodes_deleted == 0
    assert report.slot_ids == ["slot-structural"]
    assert slot.id == "slot-structural"
    assert slot.node_by_role == before_roles
    assert slot.metadata["extra_bindings"] == before_extras
    assert slot.metadata["effective_bounds"] == before_bounds
    assert slot.product_id == ""
    assert slot.metadata["product_snapshot"] == {}
    assert slot.metadata["product_binding_state"] == "empty"
    assert slot.metadata["product_content_empty"] is True
    assert document.metadata["products"] == []
    assert document.metadata["smart_slot_import_started_empty"] is True
    assert legacy.products == []
    assert legacy.pages[0].cards[0].product_id == ""
    assert legacy.pages[0].cards[0].overrides["slot_filled"] is False
    assert "slot_template_product_id" not in legacy.pages[0].cards[0].overrides

    after_visual = {
        node.id: (
            node.transform.x,
            node.transform.y,
            node.transform.width,
            node.transform.height,
            node.text,
            node.asset_id,
            node.visible,
        )
        for node in page.nodes.values()
    }
    assert after_visual == before_visual
    # A imagem visual original continua via AssetRef; apenas o marcador de
    # produto vinculado é removido.
    assert page.nodes["image"].asset_id == "asset-original"
    assert "bound_image_source" not in page.nodes["image"].metadata


def test_synthetic_autofill_image_is_emptied_but_geometry_remains() -> None:
    document, legacy, slot = _logical_reset_fixture()
    page = document.active_page
    image = page.nodes["image"]
    image.metadata["semantic_synthetic_image_slot"] = True
    image.metadata["template_hidden"] = True
    image.name = "SR Smart Image Slot"
    image.visible = True
    geometry = (
        image.transform.x,
        image.transform.y,
        image.transform.width,
        image.transform.height,
    )

    report = reset_new_pptx_import_product_content(document, legacy, source="novo.pptx")

    assert report.synthetic_images_emptied == 1
    assert image.visible is False
    assert geometry == (
        image.transform.x,
        image.transform.y,
        image.transform.width,
        image.transform.height,
    )
    assert slot.node_by_role[BindingRole.IMAGE.value] == "image"


def test_import_a_fill_then_import_b_starts_with_empty_product_state() -> None:
    assert IMPORT_A.is_file()
    assert IMPORT_B.is_file()
    service = GraphicsImportService()

    imported_a = service.import_file(IMPORT_A, project_name="Import A")
    slots_a = list(imported_a.document.active_page.slots.values())
    assert slots_a, "Import A precisa detectar pelo menos um Smart Slot"
    assert all(slot.product_id == "" for slot in slots_a)
    assert all(slot.metadata.get("product_content_empty") is True for slot in slots_a)

    session_a = GraphicsSession(imported_a.document)
    first_a = slots_a[0]
    assert CanvaBindingService.bind(
        session_a,
        first_a.id,
        {
            "id": "chosen-a",
            "display_name": "PRODUTO ESCOLHIDO A",
            "price": "12.34",
            "unit": "UN",
        },
    )
    assert first_a.product_id == "chosen-a"
    assert first_a.metadata["product_binding_state"] == "filled"

    imported_b = service.import_file(IMPORT_B, project_name="Import B")
    slots_b = [slot for page in imported_b.document.pages for slot in page.slots.values()]
    assert slots_b, "Import B precisa detectar pelo menos um Smart Slot"
    assert imported_b.document.metadata["products"] == []
    assert imported_b.legacy_project.products == []
    assert all(slot.product_id == "" for slot in slots_b)
    assert all(slot.metadata.get("product_snapshot") == {} for slot in slots_b)
    assert all(slot.metadata.get("product_binding_state") == "empty" for slot in slots_b)
    assert all(slot.metadata.get("product_content_empty") is True for slot in slots_b)
    assert all(slot.product_id != "chosen-a" for slot in slots_b)


def test_import_b_fill_save_close_reopen_preserves_b_content(tmp_path) -> None:
    imported_b = GraphicsImportService().import_file(IMPORT_B, project_name="Import B")
    page = imported_b.document.active_page
    slot = next(iter(page.slots.values()))
    image_id = slot.node_by_role.get(BindingRole.IMAGE.value, "")
    image_source = ""
    if image_id:
        image_node = page.node(image_id)
        if image_node is not None and image_node.asset_id in imported_b.document.assets:
            image_source = imported_b.document.assets[image_node.asset_id].source

    chosen_b = {
        "id": "chosen-b",
        "display_name": "PRODUTO ESCOLHIDO B",
        "price": "27.49",
        "unit": "KG",
    }
    if image_source:
        chosen_b["image_path"] = image_source

    assert CanvaBindingService.bind(GraphicsSession(imported_b.document), slot.id, chosen_b)
    assert slot.product_id == "chosen-b"
    assert slot.metadata["product_binding_state"] == "filled"
    assert slot.metadata["product_content_empty"] is False

    package = save_package(imported_b.document, tmp_path / "import-b-filled.srscene", embed_local_assets=False)
    reopened_context = load_launch_context(package)
    reopened_page = reopened_context.document.active_page
    reopened = reopened_page.slots[slot.id]

    assert reopened.product_id == "chosen-b"
    assert reopened.metadata["product_snapshot"]["display_name"] == "PRODUTO ESCOLHIDO B"
    assert reopened.metadata["product_binding_state"] == "filled"
    assert reopened.metadata["product_content_empty"] is False
    name_id = reopened.node_by_role.get(BindingRole.NAME.value, "")
    if name_id:
        assert reopened_page.nodes[name_id].text == "PRODUTO ESCOLHIDO B"
    # O marcador histórico de que o arquivo nasceu vazio pode persistir como
    # provenance; o conteúdo atual, porém, permanece preenchido após reopen.
    assert reopened_context.document.metadata["smart_slot_import_started_empty"] is True


def test_open_current_project_path_never_calls_fresh_import_reset(tmp_path, monkeypatch) -> None:
    package = tmp_path / "current-project.srscene"
    package.write_bytes(b"scene")
    prepared = SimpleNamespace(
        package_path=package,
        gate=SimpleNamespace(ready=True, score=100),
        graphics_api="auto",
        reused_session=True,
    )

    def forbidden_reset(*_args, **_kwargs):
        raise AssertionError("Abrir projeto atual não pode executar reset de nova importação")

    monkeypatch.setattr(import_bridge, "reset_new_pptx_import_product_content", forbidden_reset)
    monkeypatch.setattr(full_studio_bridge, "prepare_studio_project", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(full_studio_bridge, "_host_command", lambda: ["SRGraphicsEngine2Host.exe"])
    monkeypatch.setattr(full_studio_bridge, "_uses_current_python", lambda _command: False)

    project = StudioProject(name="Projeto atual preenchido")
    result = full_studio_bridge.launch_studio_project(
        project,
        tmp_path / "data",
        process_factory=lambda *_args, **_kwargs: _FakeProcess(),
    )

    assert result.ok is True
    assert result.launched is True
    assert result.reused_session is True
