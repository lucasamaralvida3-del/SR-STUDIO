from __future__ import annotations

from xml.etree import ElementTree as ET

from PIL import Image

from srstudio.core.models import Page, StudioProject
from srstudio.editor.canva_rendering import (
    fit_single_line_size,
    font_pixel_size,
    role_overflow_ratio,
    should_force_single_line,
    text_placement,
)
from srstudio.export.renderer import FlyerRenderer
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.reader import PptxElement
from srstudio.importers.pptx.shape_geometry import A_NS, P_NS, shape_geometry_metadata


def _custom_round_shape() -> ET.Element:
    xml = f"""
    <p:sp xmlns:p="{P_NS}" xmlns:a="{A_NS}">
      <p:spPr>
        <a:custGeom>
          <a:pathLst>
            <a:path w="783829" h="662710">
              <a:moveTo><a:pt x="143667" y="0"/></a:moveTo>
              <a:lnTo><a:pt x="640162" y="0"/></a:lnTo>
              <a:cubicBezTo><a:pt x="678265" y="0"/><a:pt x="714807" y="15136"/><a:pt x="741750" y="42079"/></a:cubicBezTo>
              <a:cubicBezTo><a:pt x="768692" y="69022"/><a:pt x="783829" y="105564"/><a:pt x="783829" y="143667"/></a:cubicBezTo>
              <a:lnTo><a:pt x="783829" y="519043"/></a:lnTo>
              <a:cubicBezTo><a:pt x="783829" y="557146"/><a:pt x="768692" y="593688"/><a:pt x="741750" y="620631"/></a:cubicBezTo>
              <a:cubicBezTo><a:pt x="714807" y="647573"/><a:pt x="678265" y="662710"/><a:pt x="640162" y="662710"/></a:cubicBezTo>
              <a:lnTo><a:pt x="143667" y="662710"/></a:lnTo>
              <a:cubicBezTo><a:pt x="105564" y="662710"/><a:pt x="69022" y="647573"/><a:pt x="42079" y="620631"/></a:cubicBezTo>
              <a:cubicBezTo><a:pt x="15136" y="593688"/><a:pt x="0" y="557146"/><a:pt x="0" y="519043"/></a:cubicBezTo>
              <a:lnTo><a:pt x="0" y="143667"/></a:lnTo>
              <a:cubicBezTo><a:pt x="0" y="105564"/><a:pt x="15136" y="69022"/><a:pt x="42079" y="42079"/></a:cubicBezTo>
              <a:cubicBezTo><a:pt x="69022" y="15136"/><a:pt x="105564" y="0"/><a:pt x="143667" y="0"/></a:cubicBezTo>
              <a:close/>
            </a:path>
          </a:pathLst>
        </a:custGeom>
      </p:spPr>
    </p:sp>
    """
    return ET.fromstring(xml)


def test_canva_points_map_to_96_dpi_page_pixels():
    assert font_pixel_size(54, 1.0) == 72
    assert font_pixel_size(18, 1.0) == 24
    assert font_pixel_size(54, 0.5) == 36


def test_split_price_tokens_stay_single_line_but_long_names_can_wrap():
    assert should_force_single_line({"text": "R$", "slot_role": "price_currency"}) is True
    assert should_force_single_line({"text": ",64", "slot_role": "price_cents"}) is True
    assert should_force_single_line({"text": "KG", "slot_role": "unit"}) is True
    assert should_force_single_line({"text": "ACÉM BOVINO", "slot_role": "name"}) is True
    assert should_force_single_line({"text": "PONTA DE PICANHA NELORE", "slot_role": "name"}) is False


def test_fitted_price_shrinks_inside_original_box_instead_of_expanding_geometry():
    size = fit_single_line_size(72, text_width=110, line_height=72, box_width=80, box_height=72)
    assert 45 <= size < 72
    assert role_overflow_ratio("price_currency") > role_overflow_ratio("name")


def test_canva_alignment_preserves_center_and_bottom():
    centered = text_placement("ctr", "ctr")
    assert centered.anchor == "center"
    assert centered.x_factor == 0.5
    assert centered.y_factor == 0.5
    bottom_right = text_placement("r", "b")
    assert bottom_right.anchor == "se"


def test_custom_canva_freeform_is_recognized_as_rounded_card():
    metadata = shape_geometry_metadata(_custom_round_shape())
    assert metadata["shape_geometry"] == "custom"
    assert 0.15 < metadata["corner_radius_ratio"] < 0.30


def test_pipeline_preserves_line_and_rounded_card_geometry():
    line = PptxElement(
        "shape",
        x=100,
        y=100,
        width=10,
        height=500,
        metadata={"shape_geometry": "line", "outline": "#470000", "line_width_px": 5.0},
    )
    converted_line = UnifiedImportPipeline._pptx_element(line, 1000, 1000, 1000, 1000)
    assert converted_line is not None
    assert converted_line["type"] == "line"
    assert converted_line["line_width"] == 5.0

    rounded = PptxElement(
        "shape",
        x=100,
        y=100,
        width=300,
        height=250,
        metadata={"shape_geometry": "custom", "corner_radius_ratio": 0.18, "fill": "#FFFFFF"},
    )
    converted = UnifiedImportPipeline._pptx_element(rounded, 1000, 1000, 1000, 1000)
    assert converted is not None
    assert converted["type"] == "rect"
    assert converted["corner_radius_ratio"] == 0.18


def test_export_renderer_handles_rounded_shape_line_and_canva_text():
    project = StudioProject()
    page = Page(name="Canva", width=320, height=400, background="#101010")
    page.elements = [
        {
            "type": "rect",
            "source": "pptx",
            "x": 30,
            "y": 30,
            "width": 150,
            "height": 120,
            "fill": "#FFFFFF",
            "outline": "",
            "corner_radius_ratio": 0.18,
            "z_index": 1,
        },
        {
            "type": "line",
            "source": "pptx",
            "x": 20,
            "y": 180,
            "width": 220,
            "height": 0,
            "outline": "#470000",
            "line_width": 5,
            "z_index": 2,
        },
        {
            "type": "text",
            "source": "pptx",
            "x": 30,
            "y": 200,
            "width": 70,
            "height": 60,
            "text": "33",
            "font_name": "Impact",
            "source_font_name": "Anton",
            "font_size": 54,
            "fill": "#FFFFFF",
            "align": "ctr",
            "vertical_anchor": "ctr",
            "slot_role": "price_integer",
            "canva_no_wrap": True,
            "z_index": 3,
        },
    ]
    project.pages = [page]
    image = FlyerRenderer().render_page(project, page)
    assert isinstance(image, Image.Image)
    assert image.size == (320, 400)
    assert image.getpixel((60, 60)) == (255, 255, 255)
