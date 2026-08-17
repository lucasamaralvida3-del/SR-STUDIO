from __future__ import annotations

from copy import deepcopy

from srstudio.graphics2.identity_repair import repair_legacy_identity_collisions
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind, SmartSlot
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.usability_gate import inspect_g2_usability


def _legacy_collision_session() -> GraphicsSession:
    document = GraphicsDocument(name="Projeto antigo")
    page = document.active_page
    name = GraphicsNode(kind=NodeKind.TEXT, text="PRODUTO")
    image = GraphicsNode(kind=NodeKind.IMAGE)
    page.add_node(name)
    page.add_node(image)
    slot = SmartSlot(
        page_id=page.id,
        node_by_role={BindingRole.NAME.value: name.id, BindingRole.IMAGE.value: image.id},
        product_id="produto-1",
    )
    page.slots[slot.id] = slot

    duplicate = deepcopy(page)
    duplicate.id = "legacy-page-copy"
    duplicate.name = "Página 2"
    for copied_slot in duplicate.slots.values():
        copied_slot.page_id = duplicate.id
    document.pages.append(duplicate)
    return GraphicsSession(document)


def test_identity_repair_rekeys_only_colliding_later_page():
    session = _legacy_collision_session()
    first = session.document.pages[0]
    second = session.document.pages[1]
    first_node_ids = set(first.nodes)
    first_slot_ids = set(first.slots)
    second_old_node_ids = set(second.nodes)
    second_old_slot_ids = set(second.slots)

    before = inspect_g2_usability(session.document)
    assert not before.professional_usable

    report = repair_legacy_identity_collisions(session)

    assert report.changed
    assert report.duplicate_node_ids == len(first_node_ids.intersection(second_old_node_ids))
    assert report.duplicate_slot_ids == len(first_slot_ids.intersection(second_old_slot_ids))
    assert len(report.repaired_pages) == 1

    repaired_first = session.document.pages[0]
    repaired_second = session.document.pages[1]
    assert set(repaired_first.nodes) == first_node_ids
    assert set(repaired_first.slots) == first_slot_ids
    assert set(repaired_second.nodes).isdisjoint(first_node_ids)
    assert set(repaired_second.slots).isdisjoint(first_slot_ids)
    assert repaired_second.name == "Página 2"

    after = inspect_g2_usability(session.document)
    assert after.professional_usable
    assert after.blockers == 0


def test_identity_repair_is_undoable():
    session = _legacy_collision_session()
    before = session.document.to_dict()

    report = repair_legacy_identity_collisions(session)
    assert report.changed
    assert session.undo()
    assert session.document.to_dict() == before


def test_identity_repair_is_noop_for_clean_document():
    document = GraphicsDocument(name="Limpo")
    document.active_page.add_node(GraphicsNode(kind=NodeKind.TEXT, text="OK"))
    session = GraphicsSession(document)

    report = repair_legacy_identity_collisions(session)

    assert not report.changed
    assert report.repaired_pages == ()
    assert report.duplicate_page_ids == 0
    assert report.duplicate_node_ids == 0
    assert report.duplicate_slot_ids == 0
