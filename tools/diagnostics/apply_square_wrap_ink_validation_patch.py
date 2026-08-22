from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "src/srstudio/graphics2/qt_renderer.py"
GENERIC_TEST = ROOT / "tests/test_graphics2_pptx_square_wrap_spautofit.py"
MEAT_TEST = ROOT / "tests/test_graphics2_quinta3_meat_square_wrap_runtime.py"


def patch_renderer() -> None:
    text = RENDERER.read_text(encoding="utf-8")
    text = text.replace("from typing import Iterable\n", "from typing import Callable, Iterable\n", 1)
    start = text.index("def _pptx_shape_autofit_wrapped_layout")
    end = text.index("\ndef _set_font_weight", start)
    replacement = '''def _pptx_grapheme_clusters(text: str, QtCore) -> list[str]:
    """Split text on Unicode grapheme boundaries using Qt's text engine."""

    value = str(text or "")
    if not value:
        return []
    boundary_type = getattr(QtCore.QTextBoundaryFinder, "Grapheme", None)
    if boundary_type is None:
        boundary_type = QtCore.QTextBoundaryFinder.BoundaryType.Grapheme
    finder = QtCore.QTextBoundaryFinder(boundary_type, value)
    finder.setPosition(0)
    boundaries = [0]
    while True:
        position = int(finder.toNextBoundary())
        if position < 0:
            break
        if position > boundaries[-1]:
            boundaries.append(position)
    if boundaries[-1] != len(value):
        boundaries.append(len(value))
    return [value[left:right] for left, right in zip(boundaries, boundaries[1:]) if right > left]


def _pptx_longest_fitting_grapheme_segments(
    text: str,
    available_width: float,
    measure_width: Callable[[str], float],
    grapheme_clusters: Callable[[str], list[str]],
) -> list[str]:
    """Emergency-wrap one residual line into the longest ink-fitting segments.

    Normal QTextLayout word wrapping runs first. This helper is used only when
    one of its residual lines still exceeds the same ink-aware width predicate
    used to select the wrapped route. At least one grapheme is emitted per
    iteration so malformed metrics cannot cause a loop.
    """

    clusters = grapheme_clusters(str(text or ""))
    if not clusters:
        return []
    width = max(0.1, float(available_width))
    tolerance = 0.01
    result: list[str] = []
    index = 0
    while index < len(clusters):
        best = index + 1
        if float(measure_width(clusters[index])) <= width + tolerance:
            end = index + 1
            while end < len(clusters):
                candidate = "".join(clusters[index : end + 1])
                if float(measure_width(candidate)) > width + tolerance:
                    break
                best = end + 1
                end += 1
        result.append("".join(clusters[index:best]))
        index = best
    return result


def _pptx_qtextlayout_fragments(text: str, available_width: float, layout_font, QtGui) -> list[str]:
    layout = QtGui.QTextLayout(text, layout_font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    fragments: list[str] = []
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(0.1, float(available_width)))
            start = int(line.textStart())
            length = int(line.textLength())
            fragment = text[start : start + length]
            if fragment:
                fragments.append(fragment)
    finally:
        layout.endLayout()
    return fragments


def _pptx_shape_autofit_wrapped_layout(text: str, rect, style: dict, font, QtCore, QtGui):
    """Lay out DrawingML ``wrap=square`` + ``spAutoFit`` text when it overflows.

    QTextLayout performs normal word wrapping first. Each returned line is then
    validated with the same ink-aware source-width metric used by route
    selection. A residual line whose glyph ink still exceeds the available
    width is split by Unicode grapheme clusters into the longest valid
    segments. Text that fits remains on the #106 explicit-baseline route.
    """

    normalized = str(text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n")
    if not normalized or "\\n" in normalized:
        return None
    if str(style.get("pptx_auto_fit") or "").lower() != "shape":
        return None
    if _should_fit_text(style):
        return None
    vertical = str(style.get("v_align") or style.get("vertical_align") or "center").lower()
    if vertical not in {"top", "t"}:
        return None
    if _pptx_effective_wrap(style) != "square":
        return None

    available_width = max(0.1, float(rect.width()))
    measure_width = lambda value: _pptx_source_layout_width(value, style, font, QtGui)
    if float(measure_width(normalized)) <= available_width + 0.01:
        return None

    layout_font = _pptx_source_layout_font(style, font, QtGui)
    qtext_fragments = _pptx_qtextlayout_fragments(normalized, available_width, layout_font, QtGui)
    fragments: list[str] = []
    for fragment in qtext_fragments:
        if float(measure_width(fragment)) <= available_width + 0.01:
            fragments.append(fragment)
            continue
        fragments.extend(
            _pptx_longest_fitting_grapheme_segments(
                fragment,
                available_width,
                measure_width,
                lambda value: _pptx_grapheme_clusters(value, QtCore),
            )
        )
    if len(fragments) <= 1:
        return None

    draw_metrics = QtGui.QFontMetricsF(font)
    line_advance = _pptx_wrapped_line_advance(style, draw_metrics)
    horizontal = str(style.get("align") or "center").lower()
    first_tight = draw_metrics.tightBoundingRect(fragments[0])
    first_baseline = float(rect.top()) - float(first_tight.top())
    result: list[tuple[str, float, float]] = []
    for index, fragment in enumerate(fragments):
        advance = float(draw_metrics.horizontalAdvance(fragment))
        if horizontal in {"left", "l"}:
            x = float(rect.left())
        elif horizontal in {"right", "r"}:
            x = float(rect.right()) - advance
        else:
            x = float(rect.left()) + (float(rect.width()) - advance) * 0.5
        result.append((fragment, x, first_baseline + line_advance * index))
    return result

'''
    text = text[:start] + replacement + text[end:]
    RENDERER.write_text(text, encoding="utf-8")


def patch_generic_test() -> None:
    text = GENERIC_TEST.read_text(encoding="utf-8")
    if "from srstudio.graphics2 import qt_renderer\n" not in text:
        text = text.replace(
            "import pytest\n\nfrom srstudio.graphics2.qt_renderer import (",
            "import pytest\n\nfrom srstudio.graphics2 import qt_renderer\nfrom srstudio.graphics2.qt_renderer import (",
            1,
        )
    marker = "def test_marginal_ink_overflow_revalidates_qtextlayout_with_grapheme_fallback"
    if marker not in text:
        text += '''\n\ndef test_marginal_ink_overflow_revalidates_qtextlayout_with_grapheme_fallback(qt, monkeypatch):
    QtCore, QtGui, _ = qt
    text = ",86"
    font = _font(QtGui)
    metrics = QtGui.QFontMetricsF(font)
    # Make the rect wider than Qt's natural advance so QTextLayout initially
    # keeps one line, while the mocked ink metric still reports source overflow.
    rect_width = float(metrics.horizontalAdvance(text)) + 1.0
    rect = QtCore.QRectF(0.0, 0.0, rect_width, 8.0)
    style = _style(font_size=18.0, font_size_unit="px")

    qtext = QtGui.QTextLayout(text, font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    qtext.setTextOption(option)
    qtext.beginLayout()
    lines = []
    try:
        while True:
            line = qtext.createLine()
            if not line.isValid():
                break
            line.setLineWidth(rect_width)
            lines.append(text[int(line.textStart()) : int(line.textStart() + line.textLength())])
    finally:
        qtext.endLayout()
    assert lines == [text]

    def ink_width(value, *_args):
        widths = {
            ",86": rect_width + 1.0,
            ",8": rect_width - 0.1,
            ",": max(1.0, rect_width * 0.35),
            "8": max(1.0, rect_width * 0.35),
            "6": max(1.0, rect_width * 0.35),
        }
        return widths[value]

    monkeypatch.setattr(qt_renderer, "_pptx_source_layout_width", ink_width)
    assert ink_width(text) > rect.width() + 0.01
    layout = qt_renderer._pptx_shape_autofit_wrapped_layout(text, rect, style, font, QtCore, QtGui)
    assert layout is not None
    assert [line for line, _, _ in layout] == [",8", "6"]
    assert "\\n" not in text
    assert qt_renderer._pptx_shape_autofit_single_line_layout(text, rect, style, font, QtGui) is None


def test_emergency_wrap_preserves_unicode_grapheme_clusters(qt):
    QtCore, _, _ = qt
    assert qt_renderer._pptx_grapheme_clusters("A\\u0301B", QtCore) == ["A\\u0301", "B"]
'''
    GENERIC_TEST.write_text(text, encoding="utf-8")


def write_meat_runtime_test() -> None:
    MEAT_TEST.write_text('''from __future__ import annotations\n\nimport os\n\nos.environ.setdefault("QT_QPA_PLATFORM", "offscreen")\n\nimport pytest\n\nfrom srstudio.graphics2 import qt_renderer\nfrom srstudio.graphics2.item_slot_host import ItemSlotCommandRouter\nfrom srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage\nfrom srstudio.graphics2.operations import GraphicsSession\nfrom srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID\nfrom srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER\n\n\nPRODUCTS = {\n    "costela": {"id": "wrap-costela", "name": "COSTELA GAÚCHA", "price": "24.86", "unit": "KG"},\n    "pernil": {"id": "wrap-pernil", "name": "PERNIL SUINO S/ OSSO", "price": "18.74", "unit": "KG"},\n    "musculo": {"id": "wrap-musculo", "name": "MÚSCULO BOVINO", "price": "32.73", "unit": "KG"},\n    "moela": {"id": "wrap-moela", "name": "MOELA DE FRANGO", "price": "16.72", "unit": "KG"},\n}\n\n\n@pytest.fixture(scope="module")\ndef qt():\n    pyside = pytest.importorskip("PySide6")\n    QtCore = pyside.QtCore\n    QtGui = pyside.QtGui\n    from PySide6.QtGui import QGuiApplication\n\n    app = QGuiApplication.instance() or QGuiApplication([])\n    return QtCore, QtGui, app\n\n\ndef _font_for(node, QtGui):\n    style = node.style\n    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")\n    base_size = max(1.0, float(style.get("font_size") or 20.0))\n    unit = str(style.get("font_size_unit") or "pt").lower()\n    logical_px = base_size * (96.0 / 72.0) if unit in {"pt", "point", "points"} else base_size\n    font = QtGui.QFont(family)\n    font.setPixelSize(max(1, round(logical_px)))\n    qt_renderer._set_font_weight(font, style.get("font_weight"), QtGui)\n    if style.get("letter_spacing") not in (None, ""):\n        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))\n    return font\n\n\ndef _bound_meat_nodes():\n    document = GraphicsDocument(name="Meat square-wrap runtime regression")\n    document.pages = [GraphicsPage(name="Página 1", width=1080.0, height=1350.0, background="#FFFFFF")]\n    document.active_page_id = document.pages[0].id\n    session = GraphicsSession(document)\n    router = ItemSlotCommandRouter(session)\n    rows = []\n    for profile_id in PROFILE_ORDER:\n        added = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})\n        assert added.ok and added.changed\n        slot = session.page.slots[added.payload["slot_id"]]\n        product = dict(PRODUCTS[profile_id])\n        product["quinta3_supervised_profile"] = profile_id\n        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})\n        assert bound.ok and bound.changed\n        rows.append((profile_id, slot))\n    return session, rows\n\n\ndef test_real_meat_nodes_use_wrapped_route_for_currency_and_decimal_when_anton_is_available(qt):\n    QtCore, QtGui, _ = qt\n    info = QtGui.QFontInfo(QtGui.QFont("Anton"))\n    if not info.exactMatch() or str(info.family()).casefold() != "anton":\n        pytest.skip("Anton is not installed in this unit-test environment; exact-SHA recert is authoritative")\n\n    session, rows = _bound_meat_nodes()\n    roles = {\n        "name": BindingRole.NAME,\n        "currency": BindingRole.CURRENCY,\n        "integer": BindingRole.PRICE_REAIS,\n        "decimal": BindingRole.PRICE_CENTS,\n        "unit": BindingRole.UNIT,\n    }\n    for profile_id, slot in rows:\n        nodes = {role: session.page.node(slot.node_by_role[binding.value]) for role, binding in roles.items()}\n        assert all(node is not None for node in nodes.values()), profile_id\n        for role in ("currency", "decimal"):\n            node = nodes[role]\n            font = _font_for(node, QtGui)\n            layout = qt_renderer._pptx_shape_autofit_wrapped_layout(\n                str(node.text or ""), QtCore.QRectF(0.0, 0.0, node.rect.width, node.rect.height), node.style, font, QtCore, QtGui\n            )\n            assert layout is not None and len(layout) > 1, (profile_id, role, node.text, node.rect)\n            assert qt_renderer._pptx_shape_autofit_single_line_layout(\n                str(node.text or ""), QtCore.QRectF(0.0, 0.0, node.rect.width, node.rect.height), node.style, font, QtGui\n            ) is None\n\n        for role in ("integer", "unit", "name"):\n            node = nodes[role]\n            font = _font_for(node, QtGui)\n            rect = QtCore.QRectF(0.0, 0.0, node.rect.width, node.rect.height)\n            assert qt_renderer._pptx_shape_autofit_wrapped_layout(\n                str(node.text or ""), rect, node.style, font, QtCore, QtGui\n            ) is None, (profile_id, role)\n            assert qt_renderer._pptx_shape_autofit_single_line_layout(\n                str(node.text or ""), rect, node.style, font, QtGui\n            ) is not None, (profile_id, role)\n''', encoding="utf-8")


def main() -> None:
    patch_renderer()
    patch_generic_test()
    write_meat_runtime_test()
    print("PATCHED=qt_renderer+generic_test+meat_runtime_test")


if __name__ == "__main__":
    main()
