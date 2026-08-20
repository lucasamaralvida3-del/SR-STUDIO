from __future__ import annotations

import os

import pytest

from srstudio.graphics2 import qt_renderer


# 18 conservative auto-wrap cases measured from the three frozen PPTX files.
# Geometry is SR Scene logical px at the imported 1080px page width. All 18
# use Anton, have no explicit newline, no rotation, and were classified as
# expected two-line wraps in the typography audit.
CORPUS_AUTOWRAP_CASES = [
    ("Quinta", 13, "TextBox 48", "COSTELINHA SUÍNA TIPO 01", 36.10, 289.621312335958, 103.73984251968504, 51.986666666666665),
    ("Quinta", 13, "TextBox 55", "BATATA MCCAIN AIRFRYER FININHAS 600G", 16.10, 188.1561154855643, 68.7867716535433, 23.186666666666667),
    ("Quinta", 14, "TextBox 109", "RONDELLI/CANELONE ANDREATTA 500G", 13.60, 161.97564304461943, 58.39191601049868, 19.586666666666666),
    ("Quinta", 14, "TextBox 112", "MANDIOCA SABOROSA PCT 1KG", 13.60, 163.21417322834648, 38.986981627296586, 19.586666666666666),
    ("Quinta", 14, "TextBox 146", "FILE DE TILAPIA BELA VIDA 500G", 13.60, 169.83884514435695, 77.79674540682414, 19.586666666666666),
    ("Quinta", 15, "TextBox 28", "LINGUIÇA MISTA CASEIRA SR", 32.92, 272.52766404199474, 142.11653543307088, 47.4),
    ("Terça", 5, "TextBox 113", "MAÇÃ NACIONAL GALA", 29.62, 245.22887139107613, 127.48020997375328, 42.653333333333336),
    ("Quarta", 7, "TextBox 90", "PÃOZINHO DE COCO CREMOSO", 13.60, 154.17942257217848, 58.39191601049868, 19.586666666666666),
    ("Quarta", 7, "TextBox 138", "TORTA DE PRESUNTO E MUSSARELA", 13.60, 166.4480839895013, 58.38267716535433, 19.586666666666666),
    ("Quarta", 8, "TextBox 61", "CEREAL MATINAL NESCAU TRADICIONAL 210G", 18.22, 237.97280839895015, 78.86330708661417, 26.24),
    ("Quarta", 8, "TextBox 66", "REQUEIJAO CANTO DE MINAS 200G", 17.42, 190.29133858267716, 75.30782152230971, 25.08),
    ("Quarta", 8, "TextBox 77", "LEITE TRIÂNGULO INTEGRAL 1L", 22.39, 191.9774278215223, 96.37553805774277, 32.24),
    ("Quarta", 8, "TextBox 83", "ACHOCOLATADO EM PÓ TODDY 370G", 13.69, 144.6992125984252, 58.766509186351705, 19.706666666666663),
    ("Quarta", 9, "TextBox 60", "CAPPUCCINO NESCAFÉ LATA 180G", 14.06, 165.72745406824149, 61.40514435695538, 20.24),
    ("Quarta", 9, "TextBox 70", "BEBIDA ALMOND BREEZE ORIGINAL 1L", 17.42, 227.50950131233594, 100.16356955380576, 25.08),
    ("Quarta", 9, "TextBox 80", "REFRIGERANTE GOLE KIDS 250ML", 16.01, 176.4114435695538, 69.07454068241469, 23.05333333333333),
    ("Quarta", 9, "TextBox 85", "CREME DE AMENDOIM BOM PRINCÍPIO 250G", 17.42, 203.00619422572177, 75.31958005249344, 25.08),
    ("Quarta", 9, "TextBox 86", "MANTEIGA RÁDIO EXTRA 500G", 21.30, 184.05280839895013, 91.54981627296587, 30.666666666666668),
]


class _Rect:
    def __init__(self, width: float, height: float, left: float = 0.0, top: float = 0.0):
        self._width = width
        self._height = height
        self._left = left
        self._top = top

    def width(self):
        return self._width

    def height(self):
        return self._height

    def left(self):
        return self._left

    def right(self):
        return self._left + self._width

    def top(self):
        return self._top

    def bottom(self):
        return self._top + self._height


class _FakeMetrics:
    def __init__(self, _font):
        pass

    def ascent(self):
        return 10.0

    def descent(self):
        return 2.0

    def height(self):
        return 12.0

    def horizontalAdvance(self, text):
        return float(len(text) * 5)


class _FakeQtGui:
    QFontMetricsF = _FakeMetrics


def test_all_18_frozen_cases_enter_custom_baseline_path(monkeypatch):
    def two_lines(text, width, font, QtGui):
        words = text.split()
        split = max(1, len(words) // 2)
        left = " ".join(words[:split]) + " "
        right = " ".join(words[split:])
        return [(left, min(width, len(left) * 5.0)), (right, min(width, len(right) * 5.0))]

    monkeypatch.setattr(qt_renderer, "_automatic_wrapped_lines", two_lines)

    seen = []
    for deck, slide, shape, text, font_size, box_w, box_h, line_spacing in CORPUS_AUTOWRAP_CASES:
        style = {
            "font_family": "Anton",
            "font_size": font_size,
            "line_spacing_px": line_spacing,
            "letter_spacing": -0.5 * 96.0 / 72.0,
            "nowrap": False,
            "align": "center",
            "v_align": "top",
        }
        layout = qt_renderer._explicit_multiline_layout(
            text,
            _Rect(box_w, box_h),
            style,
            object(),
            None,
            _FakeQtGui,
        )
        assert layout is not None, (deck, slide, shape)
        assert len(layout) == 2, (deck, slide, shape)
        assert layout[1][2] - layout[0][2] == pytest.approx(line_spacing), (deck, slide, shape)
        assert "".join(line for line, _, _ in layout).strip() == text, (deck, slide, shape)
        seen.append((deck, slide, shape))

    assert len(seen) == 18
    assert len({(deck, slide) for deck, slide, _ in seen}) == 7


def _qt():
    pytest.importorskip("PySide6")
    if os.name != "nt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(["g2-text-autowrap-test"])
    return app, QtCore, QtGui


def _font(QtGui, *, px: int = 24, tracking: float = 0.0):
    font = QtGui.QFont("Arial")
    font.setPixelSize(px)
    if tracking:
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, tracking)
    return font


def _qt_wordwrap_lines(text: str, width: float, font, QtGui):
    layout = QtGui.QTextLayout(text, font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
    layout.setTextOption(option)
    lines = []
    layout.beginLayout()
    try:
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            start = int(line.textStart())
            length = int(line.textLength())
            lines.append((text[start : start + length], float(line.naturalTextWidth())))
    finally:
        layout.endLayout()
    return lines


def test_auto_wrap_two_lines_uses_custom_baseline_advance():
    _, QtCore, QtGui = _qt()
    font = _font(QtGui, px=24)
    metrics = QtGui.QFontMetricsF(font)
    text = "ALHO A GRANEL"
    width = max(metrics.horizontalAdvance("ALHO A"), metrics.horizontalAdvance("GRANEL")) + 1.0
    assert width < metrics.horizontalAdvance(text)

    line_spacing = 31.25
    rect = QtCore.QRectF(10.0, 20.0, width, 100.0)
    layout = qt_renderer._explicit_multiline_layout(
        text,
        rect,
        {"line_spacing_px": line_spacing, "nowrap": False, "align": "center", "v_align": "top"},
        font,
        QtCore,
        QtGui,
    )
    reference = _qt_wordwrap_lines(text, width, font, QtGui)

    assert layout is not None
    assert len(layout) == 2
    assert len(reference) == 2
    assert layout[1][2] - layout[0][2] == pytest.approx(line_spacing)
    assert "".join(line for line, _, _ in layout).strip() == text
    assert [line for line, _, _ in layout] == [line for line, _ in reference]
    for (line, x, _), (reference_text, natural_width) in zip(layout, reference):
        assert line == reference_text
        assert x == pytest.approx(rect.left() + (rect.width() - natural_width) * 0.5)

    # QTextLine excludes trailing wrap-separator spaces from naturalTextWidth
    # unless IncludeTrailingSpaces is requested. QFontMetricsF on the sliced
    # string includes that space, so it is not the alignment oracle here.
    assert reference[0][0].endswith(" ")
    assert metrics.horizontalAdvance(reference[0][0]) > reference[0][1]


def test_single_line_with_custom_spacing_keeps_native_single_line_path():
    _, QtCore, QtGui = _qt()
    font = _font(QtGui, px=24)
    text = "MAÇÃ GALA"
    width = QtGui.QFontMetricsF(font).horizontalAdvance(text) + 20.0
    layout = qt_renderer._explicit_multiline_layout(
        text,
        QtCore.QRectF(0.0, 0.0, width, 60.0),
        {"line_spacing_px": 30.0, "nowrap": False, "align": "center", "v_align": "top"},
        font,
        QtCore,
        QtGui,
    )
    assert layout is None


def test_explicit_multiline_behavior_is_preserved():
    _, QtCore, QtGui = _qt()
    font = _font(QtGui, px=24)
    text = "LINGUIÇA TOSCANA\nPARA CHURRASCO"
    width = max(QtGui.QFontMetricsF(font).horizontalAdvance(part) for part in text.split("\n")) + 10.0
    line_spacing = 28.5
    layout = qt_renderer._explicit_multiline_layout(
        text,
        QtCore.QRectF(0.0, 0.0, width, 90.0),
        {"line_spacing_px": line_spacing, "nowrap": False, "align": "center", "v_align": "top"},
        font,
        QtCore,
        QtGui,
    )
    assert layout is not None
    assert [line for line, _, _ in layout] == ["LINGUIÇA TOSCANA", "PARA CHURRASCO"]
    assert layout[1][2] - layout[0][2] == pytest.approx(line_spacing)


def test_negative_tracking_participates_in_qtextlayout_wrap():
    _, _, QtGui = _qt()
    text = "CREME DE AMENDOIM BOM PRINCÍPIO 250G"
    plain = _font(QtGui, px=23, tracking=0.0)
    tracked = _font(QtGui, px=23, tracking=-0.66)

    plain_full = _qt_wordwrap_lines(text, 10000.0, plain, QtGui)
    tracked_full = _qt_wordwrap_lines(text, 10000.0, tracked, QtGui)
    assert len(plain_full) == 1
    assert len(tracked_full) == 1
    assert tracked.letterSpacingType() == QtGui.QFont.AbsoluteSpacing
    assert tracked.letterSpacing() < 0
    assert tracked_full[0][1] < plain_full[0][1]

    # Prove that the effective Qt spacing participates in wrap decisions rather
    # than requiring the getter to reproduce the requested decimal exactly.
    responsive = None
    lower = max(40, int(min(plain_full[0][1], tracked_full[0][1]) * 0.25))
    upper = int(max(plain_full[0][1], tracked_full[0][1]))
    for tenths in range(lower * 10, upper * 10 + 1):
        width = tenths / 10.0
        plain_lines = _qt_wordwrap_lines(text, width, plain, QtGui)
        tracked_lines = _qt_wordwrap_lines(text, width, tracked, QtGui)
        if [line for line, _ in plain_lines] != [line for line, _ in tracked_lines]:
            responsive = (width, plain_lines, tracked_lines)
            break

    assert responsive is not None
    _, plain_lines, tracked_lines = responsive
    assert "".join(line for line, _ in plain_lines).strip() == text
    assert "".join(line for line, _ in tracked_lines).strip() == text


def test_qfont_resolution_observation_for_corpus_families(capfd):
    _, _, QtGui = _qt()
    observations = {}
    for family in ("Anton", "High Cruiser"):
        requested = QtGui.QFont(family)
        resolved = QtGui.QFontInfo(requested).family()
        observations[family] = resolved
        print(f"G2_QFONT_OBSERVATION requested={family!r} resolved={resolved!r}")

    out, _ = capfd.readouterr()
    assert "requested='Anton'" in out
    assert "requested='High Cruiser'" in out
    assert set(observations) == {"Anton", "High Cruiser"}
