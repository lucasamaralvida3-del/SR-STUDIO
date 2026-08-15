from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal
from pathlib import Path

from srstudio.app.posters_view import PromotionPostersView, WholesalePostersView
from srstudio.app.professional_posters import SRStudioPosterProfessional
from srstudio.core.models import Product
from srstudio.posters import PosterEngine, PosterKind, PosterTemplateAnalyzer, PosterTemplateLibrary, PrintPosterService


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


def _sample_pptx(path: Path) -> None:
    presentation = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:presentation xmlns:p="{P}" xmlns:a="{A}"><p:sldSz cx="5400675" cy="7559675"/></p:presentation>'''
    shapes = "".join(
        [
            _shape(10, "CERVEJA AMSTEL LATA 12X1 350ML", 497464, 1832214, 4405745, 1543803),
            _shape(12, "R$", 225360, 3446958, 590773, 366742),
            _shape(13, "A LATA", 113047, 4280223, 768834, 366742),
            _shape(15, "3,39", 1016991, 3408089, 4017818, 1449366),
            _shape(2, "OFERTA DA economia!!!", 800000, 5600000, 3500000, 300000),
            _shape(4, "válida de 11 a 12/08/2025", 427868, 7041849, 1353560, 373783),
            _shape(3, "LIMITE DE 6CX POR CPF", 1000000, 6500000, 3000000, 300000),
            _shape(9, "R$", 225360, 5200000, 590773, 366742),
            _shape(11, "A LATA", 113047, 6100000, 768834, 366742),
            _shape(14, "3,18", 1016991, 5150000, 4017818, 1449366),
        ]
    )
    slide = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>'''
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/slides/slide1.xml", slide)


def test_promotion_data_keeps_commercial_fields_separate():
    product = Product(
        original_name="CERVEJA AMSTEL LATA 12X1 350ML",
        price="3,39",
        app_price="3,18",
        unit="UN",
        cpf_limit="6CX",
        validity="11 a 12/08/2025",
    )
    data = PosterEngine().promotion(product, "Economia")
    fields = data.fields()
    assert data.main_price == Decimal("3.39")
    assert data.club_price == Decimal("3.18")
    assert fields["main_price"] == "3,39"
    assert fields["club_price"] == "3,18"
    assert fields["main_unit"] == "A LATA"
    assert fields["limit"] == "LIMITE DE 6CX POR CPF"
    assert fields["campaign"] == "OFERTA DA Economia!!!"


def test_wholesale_data_requires_retail_wholesale_and_preserves_quantity():
    product = Product(
        original_name="ARROZ SR 5KG",
        retail_price="24,90",
        wholesale_price="22,50",
        quantity="6",
        unit="UN",
    )
    engine = PosterEngine()
    data = engine.wholesale(product)
    assert data.retail_price == Decimal("24.90")
    assert data.wholesale_price == Decimal("22.50")
    assert data.quantity == "6"
    assert not [issue for issue in engine.validate(data) if issue.severity == "error"]


def test_missing_wholesale_price_blocks_only_wholesale_poster():
    product = Product(original_name="FEIJÃO 1KG", retail_price="8,99", quantity="6")
    data = PosterEngine().wholesale(product)
    errors = [issue.field for issue in PosterEngine().validate(data) if issue.severity == "error"]
    assert "wholesale_price" in errors


def test_builtin_promotion_template_is_physical_15x21_at_300_dpi():
    template = PosterTemplateLibrary.for_kind(PosterKind.PROMOTION)[0]
    assert template.width_mm == 150
    assert template.height_mm == 210
    assert template.pixel_size == (1772, 2480)


def test_pptx_template_recognizes_reference_poster_semantics(tmp_path: Path):
    pptx = tmp_path / "cartaz-amarelo.pptx"
    _sample_pptx(pptx)
    analyzer = PosterTemplateAnalyzer()
    template = analyzer.inspect(pptx, PosterKind.PROMOTION)
    assert round(template.width_mm) == 150
    assert round(template.height_mm) == 210
    assert template.fields["product_name"].shape_id == 10
    assert template.fields["main_price"].shape_id == 15
    assert template.fields["club_price"].shape_id == 14
    assert template.fields["main_unit"].shape_id == 13
    assert template.fields["club_unit"].shape_id == 11
    assert template.fields["limit"].shape_id == 3
    assert template.fields["validity"].shape_id == 4
    assert template.fields["campaign"].shape_id == 2


def test_pptx_fill_preserves_template_and_replaces_only_mapped_text(tmp_path: Path):
    pptx = tmp_path / "model.pptx"
    _sample_pptx(pptx)
    analyzer = PosterTemplateAnalyzer()
    template = analyzer.inspect(pptx, PosterKind.PROMOTION)
    product = Product(
        original_name="ENERGETICO MONSTER 473ML",
        price="7,99",
        app_price="6,99",
        cpf_limit="6UN",
        validity="15 a 16/08/2026",
    )
    data = PosterEngine().promotion(product, "Fim de Semana")
    output = analyzer.fill(template, data, tmp_path / "filled.pptx")
    with zipfile.ZipFile(output) as archive:
        root = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
    texts = [node.text or "" for node in root.findall(f".//{{{A}}}t")]
    assert "ENERGETICO MONSTER 473ML" in texts
    assert "7,99" in texts
    assert "6,99" in texts
    assert "LIMITE DE 6UN POR CPF" in texts


def test_fallback_renderer_creates_preview_without_encartes_model():
    product = Product(original_name="CAFÉ 500G", price="19,90", app_price="17,90")
    template = PosterTemplateLibrary.for_kind(PosterKind.PROMOTION)[0]
    image = PrintPosterService().preview(product, template, "Economia", dpi=72)
    assert image.size == (425, 595)


def test_primary_poster_views_are_distinct_from_encartes_studio():
    assert PromotionPostersView.__name__ == "PromotionPostersView"
    assert WholesalePostersView.__name__ == "WholesalePostersView"
    assert SRStudioPosterProfessional.navigate is not None
    assert PromotionPostersView is not WholesalePostersView
