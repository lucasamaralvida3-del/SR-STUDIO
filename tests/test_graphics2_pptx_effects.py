from __future__ import annotations

import json
import zipfile

import pytest

from srstudio.graphics2.import_bridge import _store_pptx_effect_audit
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.pptx_effects import audit_pptx_effects, main


SLIDE_1 = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"
       xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id=\"42\" name=\"Preço principal\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:gradFill>
          <a:gsLst>
            <a:gs pos=\"0\"><a:srgbClr val=\"FF0000\"><a:alpha val=\"65000\"/></a:srgbClr></a:gs>
            <a:gs pos=\"100000\"><a:srgbClr val=\"0000FF\"/></a:gs>
          </a:gsLst>
          <a:lin ang=\"5400000\" scaled=\"1\"/>
        </a:gradFill>
        <a:effectLst>
          <a:outerShdw blurRad=\"12700\" dist=\"19050\" dir=\"5400000\" rotWithShape=\"0\"><a:srgbClr val=\"000000\"><a:alpha val=\"40000\"/></a:srgbClr></a:outerShdw>
          <a:glow rad=\"63500\"><a:srgbClr val=\"FFFFFF\"/></a:glow>
        </a:effectLst>
      </p:spPr>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

SLIDE_2 = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"
       xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld><p:spTree>
    <p:sp>
      <p:nvSpPr><p:cNvPr id=\"7\" name=\"Faixa decorativa\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr>
        <a:pattFill prst=\"pct5\"><a:fgClr><a:srgbClr val=\"0000FF\"/></a:fgClr></a:pattFill>
        <a:effectLst>
          <a:innerShdw blurRad=\"6350\"><a:srgbClr val=\"111111\"/></a:innerShdw>
          <a:reflection blurRad=\"6350\"/>
          <a:softEdge rad=\"12700\"/>
        </a:effectLst>
        <a:scene3d><a:camera prst=\"orthographicFront\"/><a:lightRig rig=\"threePt\" dir=\"t\"/></a:scene3d>
        <a:sp3d extrusionH=\"12700\"/>
      </p:spPr>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""


def _pptx(path):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/slides/slide2.xml", SLIDE_2)
        archive.writestr("ppt/slides/slide1.xml", SLIDE_1)
        archive.writestr("ppt/notesSlides/notesSlide1.xml", SLIDE_1)
    return path


def test_effect_audit_counts_and_orders_slides(tmp_path):
    report = audit_pptx_effects(_pptx(tmp_path / "effects.pptx"))

    assert [slide.slide for slide in report.slides] == [1, 2]
    first, second = report.slides
    assert first.gradient_fills == 1
    assert first.outer_shadows == 1
    assert first.glows == 1
    assert first.alpha_modifiers == 2
    assert first.advanced_effects == 3

    assert second.pattern_fills == 1
    assert second.inner_shadows == 1
    assert second.reflections == 1
    assert second.soft_edges == 1
    assert second.scene_3d == 1
    assert second.shape_3d == 1
    assert second.advanced_effects == 6

    assert report.totals["slides"] == 2
    assert report.totals["advanced_effects"] == 9
    assert report.totals["slides_with_advanced_effects"] == 2
    assert report.totals["alpha_modifiers"] == 2
    assert report.totals["slides_with_alpha"] == 1
    assert report.totals["shapes_with_advanced_effects"] == 2
    assert report.totals["shapes_with_alpha"] == 1
    assert report.totals["renderable_linear_gradients"] == 1
    assert report.totals["renderable_outer_shadows"] == 1


def test_effect_audit_attributes_effects_to_specific_shapes(tmp_path):
    report = audit_pptx_effects(_pptx(tmp_path / "effects.pptx"))

    assert len(report.shapes) == 2
    price, banner = report.shapes
    assert (price.slide, price.shape_id, price.shape_name, price.shape_kind) == (
        1,
        "42",
        "Preço principal",
        "shape",
    )
    assert price.gradient_fills == 1
    assert price.outer_shadows == 1
    assert price.glows == 1
    assert price.alpha_modifiers == 2
    assert price.advanced_effects == 3

    assert price.linear_gradient is not None
    assert price.linear_gradient["type"] == "linear"
    assert price.linear_gradient["angle"] == pytest.approx(90.0)
    assert price.linear_gradient["scaled"] is True
    assert price.linear_gradient["stops"] == [
        {"position": 0.0, "color": "#FF0000", "alpha": 0.65},
        {"position": 1.0, "color": "#0000FF", "alpha": 1.0},
    ]
    assert price.outer_shadow is not None
    assert price.outer_shadow["type"] == "outer"
    assert price.outer_shadow["color"] == "#000000"
    assert price.outer_shadow["alpha"] == pytest.approx(0.4)
    assert price.outer_shadow["blur"] == pytest.approx(12700 / 9525)
    assert price.outer_shadow["distance"] == pytest.approx(2.0)
    assert price.outer_shadow["direction"] == pytest.approx(90.0)
    assert price.outer_shadow["rot_with_shape"] is False

    assert (banner.slide, banner.shape_id, banner.shape_name) == (2, "7", "Faixa decorativa")
    assert banner.pattern_fills == 1
    assert banner.inner_shadows == 1
    assert banner.reflections == 1
    assert banner.soft_edges == 1
    assert banner.scene_3d == 1
    assert banner.shape_3d == 1
    assert banner.advanced_effects == 6
    assert banner.linear_gradient is None
    assert banner.outer_shadow is None


def test_import_bridge_persists_effect_inventory_in_scene_metadata(tmp_path):
    source = _pptx(tmp_path / "effects.pptx")
    document = GraphicsDocument(name="Effects import")

    _store_pptx_effect_audit(source, document)

    stored = document.metadata["pptx_effects"]
    assert stored["totals"]["advanced_effects"] == 9
    assert stored["totals"]["gradient_fills"] == 1
    assert stored["totals"]["outer_shadows"] == 1
    assert stored["totals"]["inner_shadows"] == 1
    assert stored["totals"]["renderable_linear_gradients"] == 1
    assert stored["totals"]["renderable_outer_shadows"] == 1
    assert stored["slides"][0]["slide"] == 1
    assert stored["shapes"][0]["shape_id"] == "42"
    assert stored["shapes"][0]["shape_name"] == "Preço principal"
    assert stored["shapes"][0]["linear_gradient"]["angle"] == pytest.approx(90.0)
    assert stored["shapes"][0]["outer_shadow"]["alpha"] == pytest.approx(0.4)


def test_import_bridge_records_effect_audit_error_without_breaking_import(tmp_path):
    source = tmp_path / "broken.pptx"
    source.write_bytes(b"not-a-zip")
    document = GraphicsDocument(name="Broken effects import")

    _store_pptx_effect_audit(source, document)

    stored = document.metadata["pptx_effects"]
    assert stored["source"].endswith("broken.pptx")
    assert stored["totals"] == {}
    assert stored["slides"] == []
    assert stored["error"]


def test_effect_audit_cli_writes_json_and_lists_shapes(tmp_path, capsys):
    source = _pptx(tmp_path / "effects.pptx")
    output = tmp_path / "audit" / "effects.json"

    assert main([str(source), "--slides", "--shapes", "--json", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["totals"]["gradient_fills"] == 1
    assert payload["totals"]["outer_shadows"] == 1
    assert payload["totals"]["pattern_fills"] == 1
    assert payload["totals"]["renderable_linear_gradients"] == 1
    assert payload["totals"]["renderable_outer_shadows"] == 1
    assert payload["slides"][0]["slide"] == 1
    assert payload["shapes"][0]["shape_id"] == "42"
    assert payload["shapes"][0]["linear_gradient"]["stops"][1]["color"] == "#0000FF"
    assert stdout_contains_effects(main, source, capsys)


def stdout_contains_effects(main_fn, source, capsys) -> bool:
    # A chamada anterior já consumiu a execução real; isolamos somente a
    # asserção de saída para manter o teste legível e explícito.
    stdout = capsys.readouterr().out
    return "PPTX Effects:" in stdout and "Preço principal" in stdout


def test_effect_audit_rejects_non_pptx(tmp_path):
    source = tmp_path / "not-a-pptx.txt"
    source.write_text("x", encoding="utf-8")

    try:
        audit_pptx_effects(source)
    except ValueError as exc:
        assert ".pptx" in str(exc)
    else:
        raise AssertionError("arquivo não-PPTX deveria ser recusado")