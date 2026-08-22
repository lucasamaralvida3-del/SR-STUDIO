from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from srstudio.graphics2 import qt_renderer
from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
from srstudio.graphics2.operations import GraphicsSession
from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID
from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER


PRODUCTS = {
    "costela": {"id": "wrap-costela", "name": "COSTELA GAÚCHA", "price": "24.86", "unit": "KG"},
    "pernil": {"id": "wrap-pernil", "name": "PERNIL SUINO S/ OSSO", "price": "18.74", "unit": "KG"},
    "musculo": {"id": "wrap-musculo", "name": "MÚSCULO BOVINO", "price": "32.73", "unit": "KG"},
    "moela": {"id": "wrap-moela", "name": "MOELA DE FRANGO", "price": "16.72", "unit": "KG"},
}


@pytest.fixture(scope="module")
def qt():
    pyside = pytest.importorskip("PySide6")
    QtCore = pyside.QtCore
    QtGui = pyside.QtGui
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    return QtCore, QtGui, app


def _font_for(node, QtGui):
    style = node.style
    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
    base_size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    logical_px = base_size * (96.0 / 72.0) if unit in {"pt", "point", "points"} else base_size
    font = QtGui.QFont(family)
    font.setPixelSize(max(1, round(logical_px)))
    qt_renderer._set_font_weight(font, style.get("font_weight"), QtGui)
    if style.get("letter_spacing") not in (None, ""):
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))
    return font


def _bound_meat_nodes():
    document = GraphicsDocument(name="Meat square-wrap runtime regression")
    document.pages = [GraphicsPage(name="Página 1", width=1080.0, height=1350.0, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)
    rows = []
    for profile_id in PROFILE_ORDER:
        added = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        assert added.ok and added.changed
        slot = session.page.slots[added.payload["slot_id"]]
        product = dict(PRODUCTS[profile_id])
        product["quinta3_supervised_profile"] = profile_id
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        assert bound.ok and bound.changed
        rows.append((profile_id, slot))
    return session, rows


def test_real_meat_nodes_use_wrapped_route_for_currency_and_decimal_when_anton_is_available(qt):
    QtCore, QtGui, _ = qt
    info = QtGui.QFontInfo(QtGui.QFont("Anton"))
    if not info.exactMatch() or str(info.family()).casefold() != "anton":
        pytest.skip("Anton is not installed in this unit-test environment; exact-SHA recert is authoritative")

    session, rows = _bound_meat_nodes()
    roles = {
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }
    for profile_id, slot in rows:
        nodes = {role: session.page.node(slot.node_by_role[binding.value]) for role, binding in roles.items()}
        assert all(node is not None for node in nodes.values()), profile_id
        for role in ("currency", "decimal"):
            node = nodes[role]
            font = _font_for(node, QtGui)
            layout = qt_renderer._pptx_shape_autofit_wrapped_layout(
                str(node.text or ""), QtCore.QRectF(0.0, 0.0, node.rect.width, node.rect.height), node.style, font, QtCore, QtGui
            )
            assert layout is not None and len(layout) > 1, (profile_id, role, node.text, node.rect)
            assert qt_renderer._pptx_shape_autofit_single_line_layout(
                str(node.text or ""), QtCore.QRectF(0.0, 0.0, node.rect.width, node.rect.height), node.style, font, QtGui
            ) is None

        for role in ("integer", "unit", "name"):
            node = nodes[role]
            font = _font_for(node, QtGui)
            rect = QtCore.QRectF(0.0, 0.0, node.rect.width, node.rect.height)
            assert qt_renderer._pptx_shape_autofit_wrapped_layout(
                str(node.text or ""), rect, node.style, font, QtCore, QtGui
            ) is None, (profile_id, role)
            assert qt_renderer._pptx_shape_autofit_single_line_layout(
                str(node.text or ""), rect, node.style, font, QtGui
            ) is not None, (profile_id, role)
