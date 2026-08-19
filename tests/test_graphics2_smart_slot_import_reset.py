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
        _node(
            "image",
            NodeKind.IMAGE,
            130,
            280,
            160,
            150,
            asset_id="asset-original",
            metadata={
                "bound_image_source": "C:/original.png",
                "template_path": "C:/original.png",
                "template_hidden": False,
            },
        ),
        _node("currency", NodeKind.TEXT, 140, 450, 32, 28, text="R$"),
        _node("reais", NodeKind.TEXT, 175, 440, 70, 44, text="9"),
        _node("cents", NodeKind.TEXT, 245, 445, 45, 30, text=",99"),
        _node("unit", NodeKind.TEXT, 250, 477, 50, 24, text="/UN"),
        _node("quantity", NodeKind.TEXT, 120, 510, 80, 26, text="3 UN"),
        _node("retail", NodeKind.TEXT, 210, 510, 80, 26, text="9,99"),
        _node("wholesale", NodeKind.TEXT, 300, 510, 80, 26, text="8,49"),
        _node("decorative", NodeKind.RECT, 90, 190, 310, 350, metadata={"purpose": "backplate"}),
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


def test_new_import_reset_preserves_structure_but_visually_empties_product_content() -> None:
    document, legacy, slot = _logical_reset_fixture()
    page = document.active_page
    before_roles = dict(slot.node_by_role)
    before_extras = dict(slot.metadata["extra_bindings"])
    before_bounds = dict(slot.metadata["effective_bounds"])
    before_geometry = {
        node.id: (
            node.transform.x,
            node.transform.y,
            node.transform.width,
            node.transform.height,
        )
        for node in page.nodes.values()
    }
    decorative_before = page.nodes["decorative"].to_dict()

    report = reset_new_pptx_import_product_content(document, legacy, source="novo.pptx")

    assert report.slots_reset == 1
    assert report.product_text_nodes_emptied >= 8
    assert report.product_images_emptied == 1
    assert report.source_text_mutations == report.product_text_nodes_emptied
    assert report.source_geometry_mutations == 0
    assert report.source_nodes_deleted == 0
    assert report.slot_ids == ["slot-structural"]
    assert slot.id == "slot-structural"
    assert slot.node_by_role == before_roles
    assert slot.metadata["extra_bindings"] == before_extras
    assert slot.metadata["effective_bounds"] == before_bounds
    assert slot.product_id == ""
    assert slot.metadata["product_snapshot"] == {}
    assert document.metadata["products"] == []
    assert document.metadata["smart_slot_import_started_empty"] is True
    assert document.metadata["smart_slot_import_reset_version"] == 2
    assert legacy.products == []
    assert legacy.pages[0].cards[0].product_id == ""
    assert legacy.pages[0].cards[0].overrides["slot_filled"] is False
    assert "slot_template_product_id" not in legacy.pages[0].cards[0].overrides

    after_geometry = {
        node.id: (
            node.transform.x,
            node.transform.y,
            node.transform.width,
            node.transform.height,
        )
        for node in page.nodes.values()
    }
    assert after_geometry == before_geometry
    assert page.nodes["decorative"].to_dict() == decorative_before

    for node_id in ["name", "currency", "reais", "cents", "unit", "quantity", "retail", "wholesale"]:
        node = page.nodes[node_id]
        assert node.text == ""
        assert node.visible is False
        assert "binding_template_text" in node.metadata

    image = page.nodes["image"]
    assert image.asset_id == ""
    assert image.visible is False
    assert image.metadata["template_product_asset_id"] == "asset-original"
    assert "bound_image_source" not in image.metadata


def test_synthetic_autofill_image_is_emptied_but_geometry_remains() -> None:
    document, legacy, slot = _logical_reset_fixture()
    image = document.active_page.nodes["image"]
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
    assert report.product_images_emptied == 1
    assert image.visible is False
    assert image.asset_id == ""
    assert geometry == (
        image.transform.x,
        image.transform.y,
        image.transform.width,
        image.transform.height,
    )
    assert slot.node_by_role[BindingRole.IMAGE.value] == "image"


def test_empty_template_reactivates_text_when_new_product_is_bound() -> None:
    document, legacy, slot = _logical_reset_fixture()
    reset_new_pptx_import_product_content(document, legacy, source="novo.pptx")
    page = document.active_page

    assert CanvaBindingService.bind(
        GraphicsSession(document),
        slot.id,
        {
            "id": "new-product",
            "display_name": "PRODUTO NOVO",
            "price": "12.34",
            "unit": "KG",
        },
    )

    assert page.nodes["name"].text == "PRODUTO NOVO"
    assert page.nodes["name"].visible is True
    assert page.nodes["reais"].text == "12"
    assert page.nodes["reais"].visible is True
    assert page.nodes["image"].visible is False
    assert page.nodes["image"].asset_id == ""


def test_import_a_fill_then_import_b_starts_with_empty_product_state() -> None:
    assert IMPORT_A.is_file()
    assert IMPORT_B.is_file()
    service = GraphicsImportService()

    imported_a = service.import_file(IMPORT_A, project_name="Import A")
    slots_a = list(imported_a.document.active_page.slots.values())
    assert slots_a
    assert all(slot.product_id == "" for slot in slots_a)
    assert all(slot.metadata.get("product_snapshot") == {} for slot in slots_a)

    first_a = slots_a[0]
    assert CanvaBindingService.bind(
        GraphicsSession(imported_a.document),
        first_a.id,
        {
            "id": "chosen-a",
            "display_name": "PRODUTO ESCOLHIDO A",
            "price": "12.34",
            "unit": "UN",
        },
    )
    assert first_a.product_id == "chosen-a"
    assert first_a.metadata["product_snapshot"]["id"] == "chosen-a"

    imported_b = service.import_file(IMPORT_B, project_name="Import B")
    slots_b = [slot for page in imported_b.document.pages for slot in page.slots.values()]
    assert slots_b
    assert imported_b.document.metadata["products"] == []
    assert imported_b.legacy_project.products == []
    assert all(slot.product_id == "" for slot in slots_b)
    assert all(slot.metadata.get("product_snapshot") == {} for slot in slots_b)
    assert all(slot.product_id != "chosen-a" for slot in slots_b)

    for page in imported_b.document.pages:
        for slot_b in page.slots.values():
            for node_id in slot_b.node_by_role.values():
                node = page.node(node_id)
                if node is None:
                    continue
                if node.kind is NodeKind.TEXT:
                    assert node.text == ""
                elif node.kind is NodeKind.IMAGE:
                    assert node.visible is False


def test_import_b_fill_save_close_reopen_preserves_b_content(tmp_path) -> None:
    imported_b = GraphicsImportService().import_file(IMPORT_B, project_name="Import B")
    page = imported_b.document.active_page
    slot = next(iter(page.slots.values()))

    chosen_b = {
        "id": "chosen-b",
        "display_name": "PRODUTO ESCOLHIDO B",
        "price": "27.49",
        "unit": "KG",
    }
    image_id = slot.node_by_role.get(BindingRole.IMAGE.value, "")
    template_asset_id = ""
    if image_id:
        image_node = page.node(image_id)
        if image_node is not None:
            template_asset_id = str(image_node.metadata.get("template_product_asset_id") or "")
    if template_asset_id and template_asset_id in imported_b.document.assets:
        chosen_b["image_path"] = imported_b.document.assets[template_asset_id].source

    assert CanvaBindingService.bind(GraphicsSession(imported_b.document), slot.id, chosen_b)
    assert slot.product_id == "chosen-b"
    assert slot.metadata["product_snapshot"]["id"] == "chosen-b"

    package = save_package(imported_b.document, tmp_path / "import-b-filled.srscene", embed_local_assets=False)
    reopened_context = load_launch_context(package)
    reopened_page = reopened_context.document.active_page
    reopened = reopened_page.slots[slot.id]

    assert reopened.product_id == "chosen-b"
    assert reopened.metadata["product_snapshot"]["display_name"] == "PRODUTO ESCOLHIDO B"
    name_id = reopened.node_by_role.get(BindingRole.NAME.value, "")
    if name_id:
        assert reopened_page.nodes[name_id].text == "PRODUTO ESCOLHIDO B"
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

    result = full_studio_bridge.launch_studio_project(
        StudioProject(name="Projeto atual preenchido"),
        tmp_path / "data",
        process_factory=lambda *_args, **_kwargs: _FakeProcess(),
    )

    assert result.ok is True
    assert result.launched is True
    assert result.reused_session is True
