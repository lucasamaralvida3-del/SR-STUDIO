from __future__ import annotations

import json
import zipfile

from srstudio.graphics2.import_bridge import _store_pptx_effect_audit
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.pptx_effects import audit_pptx_effects, main


SLIDE_1 = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"
       xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld><p:spTree>
    <p:sp><p:spPr>
      <a:gradFill><a:gsLst><a:gs pos=\"0\"><a:srgbClr val=\"FF0000\"><a:alpha val=\"65000\"/></a:srgbClr></a:gs></a:gsLst></a:gradFill>
      <a:effectLst>
        <a:outerShdw blurRad=\"12700\" dist=\"12700\" dir=\"5400000\"><a:srgbClr val=\"000000\"><a:alpha val=\"40000\"/></a:srgbClr></a:outerShdw>
        <a:glow rad=\"63500\"><a:srgbClr val=\"FFFFFF\"/></a:glow>
      </a:effectLst>
    </p:spPr></p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

SLIDE_2 = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\"
       xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\">
  <p:cSld><p:spTree>
    <p:sp><p:spPr>
      <a:pattFill prst=\"pct5\"><a:fgClr><a:srgbClr val=\"0000FF\"/></a:fgClr></a:pattFill>
      <a:effectLst>
        <a:innerShdw blurRad=\"6350\"><a:srgbClr val=\"111111\"/></a:innerShdw>
        <a:reflection blurRad=\"6350\"/>
        <a:softEdge rad=\"12700\"/>
      </a:effectLst>
      <a:scene3d><a:camera prst=\"orthographicFront\"/><a:lightRig rig=\"threePt\" dir=\"t\"/></a:scene3d>
      <a:sp3d extrusionH=\"12700\"/>
    </p:spPr></p:sp>
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


def test_import_bridge_persists_effect_inventory_in_scene_metadata(tmp_path):
    source = _pptx(tmp_path / "effects.pptx")
    document = GraphicsDocument(name="Effects import")

    _store_pptx_effect_audit(source, document)

    stored = document.metadata["pptx_effects"]
    assert stored["totals"]["advanced_effects"] == 9
    assert stored["totals"]["gradient_fills"] == 1
    assert stored["totals"]["outer_shadows"] == 1
    assert stored["totals"]["inner_shadows"] == 1
    assert stored["slides"][0]["slide"] == 1


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


def test_effect_audit_cli_writes_json(tmp_path, capsys):
    source = _pptx(tmp_path / "effects.pptx")
    output = tmp_path / "audit" / "effects.json"

    assert main([str(source), "--slides", "--json", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["totals"]["gradient_fills"] == 1
    assert payload["totals"]["outer_shadows"] == 1
    assert payload["totals"]["pattern_fills"] == 1
    assert payload["slides"][0]["slide"] == 1
    assert "PPTX Effects:" in capsys.readouterr().out


def test_effect_audit_rejects_non_pptx(tmp_path):
    source = tmp_path / "not-a-pptx.txt"
    source.write_text("x", encoding="utf-8")

    try:
        audit_pptx_effects(source)
    except ValueError as exc:
        assert ".pptx" in str(exc)
    else:
        raise AssertionError("arquivo não-PPTX deveria ser recusado")
