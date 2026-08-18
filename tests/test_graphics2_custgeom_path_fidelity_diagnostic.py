from __future__ import annotations

from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from srstudio.graphics2 import pptx_fidelity
from srstudio.graphics2 import qt_renderer

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _shape(*, width: int, height: int, right: int, bottom: int):
    return ET.fromstring(
        f"""
        <p:sp xmlns:p="{P_NS}" xmlns:a="{A_NS}">
          <p:spPr>
            <a:custGeom>
              <a:avLst/>
              <a:gdLst/>
              <a:ahLst/>
              <a:cxnLst/>
              <a:rect l="l" t="t" r="r" b="b"/>
              <a:pathLst>
                <a:path w="{width}" h="{height}">
                  <a:moveTo><a:pt x="0" y="0"/></a:moveTo>
                  <a:lnTo><a:pt x="{right}" y="0"/></a:lnTo>
                  <a:lnTo><a:pt x="{right}" y="{bottom}"/></a:lnTo>
                  <a:lnTo><a:pt x="0" y="{bottom}"/></a:lnTo>
                  <a:lnTo><a:pt x="0" y="0"/></a:lnTo>
                  <a:close/>
                </a:path>
              </a:pathLst>
            </a:custGeom>
          </p:spPr>
        </p:sp>
        """
    )


@pytest.mark.parametrize(
    ("width", "height", "right", "bottom"),
    [
        # Real frozen-corpus signatures: the path viewport differs from the
        # final coordinate by exactly one EMU in one axis.
        (10_515_734, 7_319_202, 10_515_734, 7_319_203),
        (10_460_819, 6_969_521, 10_460_820, 6_969_521),
        (2_791_013, 2_791_013, 2_791_012, 2_791_012),
    ],
)
def test_frozen_corpus_mlz_path_preserves_viewport_and_points(width, height, right, bottom):
    spec = pptx_fidelity._custom_path_spec(_shape(width=width, height=height, right=right, bottom=bottom))

    assert spec is not None
    assert spec["width"] == float(width)
    assert spec["height"] == float(height)
    assert len(spec["paths"]) == 1
    path = spec["paths"][0]
    assert path["width"] == float(width)
    assert path["height"] == float(height)
    assert [item["op"] for item in path["commands"]] == ["M", "L", "L", "L", "L", "Z"]
    assert path["commands"][1]["points"][0] == [float(right), 0.0]
    assert path["commands"][2]["points"][0] == [float(right), float(bottom)]
    assert not pptx_fidelity._path_is_axis_aligned_rect(spec)


class _Point:
    def __init__(self, x: float, y: float):
        self.x = float(x)
        self.y = float(y)


class _PainterPath:
    def __init__(self):
        self.commands: list[tuple] = []

    def moveTo(self, point):
        self.commands.append(("M", point.x, point.y))

    def lineTo(self, point):
        self.commands.append(("L", point.x, point.y))

    def cubicTo(self, a, b, c):
        self.commands.append(("C", a.x, a.y, b.x, b.y, c.x, c.y))

    def quadTo(self, a, b):
        self.commands.append(("Q", a.x, a.y, b.x, b.y))

    def closeSubpath(self):
        self.commands.append(("Z",))

    def isEmpty(self):
        return not self.commands


class _QtGui:
    QPainterPath = _PainterPath


class _Target:
    def __init__(self, x: float, y: float, width: float, height: float):
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._width

    def height(self):
        return self._height


def test_qt_custom_path_keeps_one_emu_viewport_delta(monkeypatch):
    width, height = 10_515_734, 7_319_202
    right, bottom = 10_515_734, 7_319_203
    spec = pptx_fidelity._custom_path_spec(_shape(width=width, height=height, right=right, bottom=bottom))
    assert spec is not None

    monkeypatch.setattr(qt_renderer, "QtCorePoint", lambda x, y, _qt_gui: _Point(x, y))
    target = _Target(10.0, 20.0, 400.0, 300.0)
    path = qt_renderer._custom_path(spec, target, _QtGui)

    assert path is not None
    assert [item[0] for item in path.commands] == ["M", "L", "L", "L", "L", "Z"]
    assert path.commands[1][1:] == pytest.approx((410.0, 20.0))
    # The source bottom is one EMU beyond the declared path viewport; Qt must
    # preserve that fact instead of normalizing/clamping it to target.bottom().
    expected_bottom = 20.0 + bottom * (300.0 / height)
    assert path.commands[2][1:] == pytest.approx((410.0, expected_bottom))
    assert expected_bottom > 320.0
