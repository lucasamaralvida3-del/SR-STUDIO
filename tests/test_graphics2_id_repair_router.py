from __future__ import annotations

import copy

from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot, Transform
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity


def _legacy_document() -> GraphicsDocument:
    document = GraphicsDocument(name="Legacy editor repair")
    first = document.active_page
    first.name = "Página 1"
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        text="ARROZ PATOSUL 5KG",
        transform=Transform(x=100, y=120, width=300, height=60),
    )
    first.add_node(name)
    slot = SmartSlot(
        name="Produto 1",
        page_id=first.id,
        node_by_role={BindingRole.NAME.value: name.id},
        product_id="p1",
    )
    first.slots[slot.id] = slot
    card_id = f"productcard:{slot.id}"
    slot.metadata["semantic_product_card_id"] = card_id
    first.metadata["semantic_blocks"] = {
        card_id: {
            "id": card_id,
            "kind": "product_card",
            "slot_id": slot.id,
            "members": [name.id],
            "roles": {BindingRole.NAME.value: [name.id]},
            "metadata": {
                "smart_slot_id": slot.id,
                "content_members": [name.id],
                "recovered": True,
                "atomic": True,
            },
        }
    }
    name.metadata["semantic_product_card_id"] = card_id

    second = copy.deepcopy(first)
    second.id = "page_legacy_duplicate"
    second.name = "Página 2"
    for current_slot in second.slots.values():
        current_slot.page_id = second.id
    document.pages.append(second)
    document.active_page_id = second.id
    document.metadata["products"] = [
        {"id": "p1", "display_name": "ARROZ PATOSUL 5KG", "price": "25,77", "unit": "UN"}
    ]
    return document


def test_router_repairs_legacy_ids_then_edit_save_reopen_stays_valid(tmp_path):
    router = GraphicsCommandRouter(GraphicsSession(_legacy_document()))

    assert router.integrity_repair.changed
    assert router.integrity_repair.pages_rebuilt == 1
    payload = router.payload()
    assert payload["editor"]["integrity_repair"]["changed"] is True
    assert payload["editor"]["integrity_repair"]["pages_rebuilt"] == 1
    assert_document_integrity(router.session.document)

    active = router.session.page
    assert active.name == "Página 2"
    slot = next(iter(active.slots.values()))
    name_id = slot.node_by_role[BindingRole.NAME.value]
    selected = router.dispatch({"name": "select", "node_id": name_id, "semantic": True, "semantic_scope": "card"})
    assert selected.ok
    before_x = active.node(name_id).transform.x
    moved = router.dispatch({"name": "move", "dx": 17, "dy": 9, "snap": False})
    assert moved.ok and moved.changed
    assert router.session.page.node(name_id).transform.x == before_x + 17

    project = tmp_path / "legacy-repaired.srscene"
    save_package(router.session.document, project, embed_local_assets=True)
    reopened = load_package(project, extract_assets_to=tmp_path / "assets")
    assert_document_integrity(reopened)
    assert len(reopened.pages) == 2
    assert reopened.metadata["g2_integrity_migrations"][-1]["kind"] == "legacy-cross-page-id-repair"

    second_router = GraphicsCommandRouter(GraphicsSession(reopened))
    assert not second_router.integrity_repair.changed
    assert_document_integrity(second_router.session.document)
    reopened_active = second_router.session.page
    reopened_slot = next(iter(reopened_active.slots.values()))
    reopened_name = reopened_active.node(reopened_slot.node_by_role[BindingRole.NAME.value])
    assert reopened_name is not None
    assert reopened_name.transform.x == before_x + 17


def test_router_repair_does_not_create_undo_step_for_open_time_migration():
    router = GraphicsCommandRouter(GraphicsSession(_legacy_document()))

    assert router.integrity_repair.changed
    assert not router.session.history.can_undo
    assert not router.session.history.can_redo
    assert router.dispatch({"name": "undo"}).changed is False
