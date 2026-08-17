from __future__ import annotations

import copy

from srstudio.graphics2.id_repair import repair_legacy_cross_page_ids
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, SmartSlot, NodeKind, Transform
from srstudio.graphics2.preflight import assert_document_integrity, run_preflight


def _document_with_legacy_collision() -> GraphicsDocument:
    document = GraphicsDocument(name="Legacy duplicated pages")
    first = document.active_page
    node = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome",
        text="ARROZ PATOSUL 5KG",
        transform=Transform(x=100, y=120, width=300, height=60),
        style={"font_family": "Arial", "font_size": 28},
    )
    first.add_node(node)
    slot = SmartSlot(
        name="Produto",
        page_id=first.id,
        node_by_role={BindingRole.NAME.value: node.id},
        product_id="p1",
    )
    first.slots[slot.id] = slot
    card_id = f"productcard:{slot.id}"
    first.metadata["semantic_blocks"] = {
        card_id: {
            "id": card_id,
            "kind": "product_card",
            "slot_id": slot.id,
            "members": [node.id],
            "roles": {BindingRole.NAME.value: [node.id]},
            "metadata": {"smart_slot_id": slot.id, "content_members": [node.id]},
        }
    }
    slot.metadata["semantic_product_card_id"] = card_id
    node.metadata["semantic_product_card_id"] = card_id

    # Simula exatamente a duplicação antiga: página nova, IDs internos iguais.
    second = copy.deepcopy(first)
    second.id = "page_legacy_copy"
    second.name = "Página 2"
    for current_slot in second.slots.values():
        current_slot.page_id = second.id
    document.pages.append(second)
    document.active_page_id = second.id
    return document


def _visual_signature(page) -> tuple:
    return tuple(
        sorted(
            (
                node.name,
                node.text,
                node.kind.value,
                node.transform.x,
                node.transform.y,
                node.transform.width,
                node.transform.height,
                node.transform.rotation,
                node.z_index,
                node.visible,
                node.opacity,
            )
            for node in page.nodes.values()
        )
    )


def test_repair_legacy_cross_page_ids_is_conservative_idempotent_and_auditable():
    document = _document_with_legacy_collision()
    before_second_visual = _visual_signature(document.pages[1])
    codes = {issue.code for issue in run_preflight(document)}
    assert "DUPLICATE_NODE_ID" in codes
    assert "DUPLICATE_SLOT_ID" in codes
    assert "DUPLICATE_SEMANTIC_ID" in codes

    old_second_id = document.pages[1].id
    report = repair_legacy_cross_page_ids(document)

    assert report.changed
    assert report.pages_rebuilt == 1
    assert report.repairs[0]["old_page_id"] == old_second_id
    assert set(report.repairs[0]["reasons"]) == {
        "duplicate_node_id",
        "duplicate_slot_id",
        "duplicate_semantic_id",
    }
    assert document.pages[1].id != old_second_id
    assert document.active_page_id == document.pages[1].id
    assert _visual_signature(document.pages[1]) == before_second_visual
    assert_document_integrity(document)

    first, second = document.pages
    assert set(first.nodes).isdisjoint(second.nodes)
    assert set(first.slots).isdisjoint(second.slots)
    assert set(first.metadata["semantic_blocks"]).isdisjoint(second.metadata["semantic_blocks"])
    assert document.metadata["g2_integrity_migrations"][-1]["kind"] == "legacy-cross-page-id-repair"

    second_report = repair_legacy_cross_page_ids(document)
    assert not second_report.changed
    assert second_report.pages_rebuilt == 0
    assert len(document.metadata["g2_integrity_migrations"]) == 1


def test_duplicate_page_id_keeps_first_occurrence_as_unambiguous_active_target():
    document = _document_with_legacy_collision()
    first = document.pages[0]
    second = document.pages[1]
    second.id = first.id
    for slot in second.slots.values():
        slot.page_id = second.id
    document.active_page_id = first.id

    report = repair_legacy_cross_page_ids(document)

    assert report.changed
    assert "duplicate_page_id" in report.repairs[0]["reasons"]
    assert document.pages[0].id == first.id
    assert document.pages[1].id != first.id
    assert document.active_page_id == first.id
    assert_document_integrity(document)
