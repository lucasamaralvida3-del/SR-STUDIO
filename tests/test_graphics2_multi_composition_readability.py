from srstudio.graphics2.model import GraphicsDocument, BindingRole
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.promotion_composition import apply_slot_composition
from srstudio.graphics2.promotion_layouts import plan_promotion
from srstudio.graphics2.item_slots import _builtins


def test_composed_multi_prices_are_readable_without_changing_source_preset():
    session = GraphicsSession(GraphicsDocument())
    plan = plan_promotion("seven")
    first = apply_slot_composition(session, plan)
    multis = [session.page.slots[sid] for sid in first.slot_ids
              if session.page.slots[sid].metadata.get("multi_parent_id")]
    assert len(multis) == 4
    for slot in multis:
        integer = session.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value])
        assert integer.style["font_size"] == 46
        assert integer.style["fit_inside_box"]
    apply_slot_composition(session, plan)
    for slot in multis:
        assert session.page.node(slot.node_by_role[BindingRole.PRICE_REAIS.value]).style["font_size"] == 46
    assert _builtins()["multi-cell-beta44"].roles["integer"]["style"]["font_size"] == 35.6
