from __future__ import annotations

from xml.etree import ElementTree as ET

from srstudio.graphics2.image_crop import crop_pixel_box
from srstudio.graphics2.image_fill import drawingml_fill_destination
from srstudio.importers.pptx.reader import PptxImporter

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def test_frozen_corpus_pattern_absent_srcrect_keeps_full_source_before_fillrect():
    # Real frozen-corpus pattern: blipFill has no a:srcRect, but may have a
    # non-zero a:stretch/a:fillRect. In that case source crop must be identity
    # and only the destination rectangle changes.
    blip_fill = ET.fromstring(
        f"""
        <a:blipFill xmlns:a="{A_NS}">
          <a:blip/>
          <a:stretch>
            <a:fillRect l="-30959" t="0" r="-30437" b="0"/>
          </a:stretch>
        </a:blipFill>
        """
    )

    src_rect = blip_fill.find(f"{{{A_NS}}}srcRect")
    fill_rect = blip_fill.find(f".//{{{A_NS}}}fillRect")

    crop = PptxImporter._rect_percent(src_rect)
    fill = PptxImporter._rect_percent(fill_rect)

    assert crop == {}
    assert fill == {"l": -0.30959, "t": 0.0, "r": -0.30437, "b": 0.0}
    assert crop_pixel_box(1920, 1080, crop) == (0, 0, 1920, 1080)

    destination = drawingml_fill_destination(400.0, 300.0, fill)
    assert destination.x < 0.0
    assert destination.width > 400.0
    assert destination.y == 0.0
    assert destination.height == 300.0
