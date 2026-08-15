from __future__ import annotations

import zipfile
from pathlib import Path

from srstudio.posters import PosterKind, PosterTemplateAnalyzer


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _shape(shape_id: int, text: str, x: int, y: int, cx: int, cy: int) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr><p:cNvPr id="{shape_id}" name="Shape {shape_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
      <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm></p:spPr>
      <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody>
    </p:sp>
    """


def test_off_canvas_limit_note_does_not_replace_real_printed_limit(tmp_path: Path):
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:presentation xmlns:p="{P}" xmlns:a="{A}"><p:sldSz cx="5400675" cy="7559675"/></p:presentation>'''
    shapes = "".join(
        [
            _shape(10, "CERVEJA AMSTEL LATA 350ML", 497464, 1832214, 4405745, 1543803),
            _shape(12, "R$", 225360, 3446958, 590773, 366742),
            _shape(15, "3,39", 1016991, 3408089, 4017818, 1449366),
            _shape(13, "A LATA", 113047, 4280223, 768834, 366742),
            # Same helper note arrangement used by the user's real poster PPTX:
            # it lives completely to the left of the printable slide.
            _shape(24, "LIMITE DE CIMA OFERTA", -2645384, 1445846, 2474562, 276665),
            _shape(3, "LIMITE DE 6CX POR CPF", 1781428, 5131829, 1843594, 148814),
        ]
    )
    slide = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>'''
    pptx = tmp_path / "poster.pptx"
    with zipfile.ZipFile(pptx, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/slides/slide1.xml", slide)

    template = PosterTemplateAnalyzer().inspect(pptx, PosterKind.PROMOTION)
    assert template.fields["limit"].shape_id == 3
    assert template.metadata["ignored_helper_shapes"] == 1
