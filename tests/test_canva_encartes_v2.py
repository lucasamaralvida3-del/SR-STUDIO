from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image

from srstudio.core.models import Product, ProductCard
from srstudio.editor.product_cards import ProductCardRegistry
from srstudio.images.canva_training import CanvaTrainingService
from srstudio.images.library import ImageLibrary
from srstudio.importers.pptx.reader import PptxElement, PptxImportResult, PptxImporter, PptxSlide
from srstudio.importers.pptx.semantic import SemanticMapper
from srstudio.templates.corpus import LayoutCorpus


def _png(path: Path, size=(240, 320), value=170) -> Path:
    Image.new("RGB", size, (value, 90, 40)).save(path, "PNG")
    return path


def _semantic_slide(image_path: Path) -> PptxSlide:
    elements = [
        PptxElement("text", 120, 90, 410, 70, "ARROZ VASCONCELOS 5KG", metadata={"font_name": "Anton", "font_size_pt": 24.0, "fill": "#105594"}),
        PptxElement("image", 120, 180, 330, 230, media_path=str(image_path), metadata={"picture_fill": True, "crop": {"l": 0.02, "t": 0.0, "r": 0.02, "b": 0.0}}),
        PptxElement("text", 130, 440, 45, 36, "R$"),
        PptxElement("text", 180, 425, 110, 90, "15", metadata={"font_name": "Anton", "font_size_pt": 42.0, "fill": "#105594"}),
        PptxElement("text", 294, 438, 70, 45, ",21", metadata={"font_name": "Anton", "font_size_pt": 20.0, "fill": "#105594"}),
        PptxElement("text", 365, 446, 58, 34, "UN"),
        PptxElement("text", 12, 12, 260, 55, "OFERTAS DA ECONOMIA"),
    ]
    return PptxSlide(index=1, width=1000, height=1250, elements=elements)


def test_semantic_mapper_reconstructs_split_canva_price_and_card(tmp_path):
    image_path = _png(tmp_path / "arroz.png")
    slide = _semantic_slide(image_path)
    cards = SemanticMapper().map_slide(slide)
    assert len(cards) == 1
    card = cards[0]
    assert str(card.price_value) == "15.21"
    assert card.name is not None and card.name.text == "ARROZ VASCONCELOS 5KG"
    assert card.image is not None and card.image.media_path == str(image_path)
    assert card.unit is not None and card.unit.text == "UN"
    assert card.price_cluster is not None
    assert card.price_cluster.currency is not None
    assert card.price_cluster.integer is not None
    assert card.price_cluster.cents is not None
    assert card.confidence >= 0.90
    assert card.style_spec["image_region"]
    assert card.style_spec["price_region"]


def test_canva_reader_recognizes_picture_fill_and_applies_group_transform(tmp_path):
    source_image = _png(tmp_path / "source.png", (64, 64))
    pptx = tmp_path / "canva.pptx"
    presentation = """<?xml version="1.0" encoding="UTF-8"?>
    <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
      <p:sldSz cx="10000000" cy="12500000"/>
    </p:presentation>"""
    slide = """<?xml version="1.0" encoding="UTF-8"?>
    <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
           xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
           xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <p:cSld><p:spTree>
        <p:nvGrpSpPr><p:cNvPr id="1" name="root"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
        <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="10000000" cy="12500000"/><a:chOff x="0" y="0"/><a:chExt cx="10000000" cy="12500000"/></a:xfrm></p:grpSpPr>
        <p:grpSp>
          <p:nvGrpSpPr><p:cNvPr id="2" name="Card Group"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
          <p:grpSpPr><a:xfrm><a:off x="1000000" y="1000000"/><a:ext cx="2000000" cy="2000000"/><a:chOff x="0" y="0"/><a:chExt cx="1000" cy="1000"/></a:xfrm></p:grpSpPr>
          <p:sp>
            <p:nvSpPr><p:cNvPr id="3" name="Freeform Image"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
            <p:spPr>
              <a:xfrm><a:off x="100" y="100"/><a:ext cx="300" cy="300"/></a:xfrm>
              <a:blipFill><a:blip r:embed="rId1"/><a:srcRect l="1000" r="2000"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>
            </p:spPr>
          </p:sp>
        </p:grpSp>
        <p:sp>
          <p:nvSpPr><p:cNvPr id="4" name="Product Name"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
          <p:spPr><a:xfrm><a:off x="1000000" y="4500000"/><a:ext cx="3000000" cy="600000"/></a:xfrm><a:solidFill><a:srgbClr val="105594"/></a:solidFill></p:spPr>
          <p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr sz="2400" b="1"><a:latin typeface="Anton"/></a:rPr><a:t>ARROZ VASCONCELOS 5KG</a:t></a:r></a:p></p:txBody>
        </p:sp>
      </p:spTree></p:cSld>
    </p:sld>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
    </Relationships>"""
    with zipfile.ZipFile(pptx, "w") as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        archive.write(source_image, "ppt/media/image1.png")

    result = PptxImporter().import_file(pptx, media_dir=tmp_path / "media")
    assert not result.warnings
    assert len(result.slides) == 1
    images = [element for element in result.slides[0].elements if element.kind == "image"]
    assert len(images) == 1
    image = images[0]
    assert image.metadata["picture_fill"] is True
    assert Path(image.media_path).is_file()
    assert image.metadata["grouped"] is True
    assert image.metadata["group_depth"] == 1
    assert image.x == 1_200_000
    assert image.y == 1_200_000
    assert image.width == 600_000
    assert image.height == 600_000
    assert round(image.metadata["crop"]["l"], 3) == 0.01
    text = next(element for element in result.slides[0].elements if element.kind == "text")
    assert text.metadata["font_name"] == "Anton"
    assert text.metadata["font_size_pt"] == 24.0


def test_image_library_learns_deduplicates_and_fuzzy_matches_products(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    source = _png(tmp_path / "arroz.png")
    first = library.learn_product_image(source, "ARROZ VASCONCELOS 5KG", confidence=0.95, source_file="Economia.pptx", slide_index=1)
    second = library.learn_product_image(source, "ARROZ VASCONCELOS 5KG", confidence=0.96, source_file="Fim de Semana.pptx", slide_index=3)
    assert first.id == second.id
    assert library.stats()["products"] == 1
    assert library.stats()["accepted"] == 1
    match = library.find_best_for_product("ARROZ VASCONCELOS T1 5KG")
    assert match is not None
    assert match.asset.id == first.id
    assert match.score >= library.AUTO_MATCH_SCORE
    library.set_preferred(first.id, True)
    assert library.find_for_product("ARROZ VASCONCELOS 5KG")[0].preferred is True


def test_low_confidence_canva_image_goes_to_review(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    source = _png(tmp_path / "produto.png")
    asset = library.learn_product_image(source, "PRODUTO TESTE 500G", confidence=0.70)
    assert asset.review_status == "pending"
    assert len(library.pending_review()) == 1
    library.set_review_status(asset.id, "accepted")
    assert library.stats()["accepted"] == 1


def test_layout_corpus_merges_similar_sr_pages(tmp_path):
    image_path = _png(tmp_path / "arroz.png")
    mapper = SemanticMapper()
    first_slide = _semantic_slide(image_path)
    second_slide = _semantic_slide(image_path)
    # Tiny normal layout drift should be learned as the same pattern.
    for element in second_slide.elements:
        if element.kind in {"text", "image"} and element.y > 80:
            element.x += 4
            element.y += 3
    corpus = LayoutCorpus(tmp_path / "layouts.json")
    first = corpus.observe(first_slide, mapper.map_slide(first_slide), "OFERTAS DA ECONOMIA NOVA.pptx")
    second = corpus.observe(second_slide, mapper.map_slide(second_slide), "OFERTAS DA ECONOMIA NOVA.pptx")
    assert first is not None and second is not None
    assert first.id == second.id
    assert corpus.stats()["profiles"] == 1
    assert corpus.stats()["samples"] == 2
    assert corpus.all()[0].campaign == "ECONOMIA"
    assert corpus.all()[0].fonts.get("Anton", 0) >= 2


def test_training_service_populates_image_bank_and_layouts_without_loading_project(tmp_path, monkeypatch):
    source_image = _png(tmp_path / "arroz.png")
    slide = _semantic_slide(source_image)
    fake_pptx = tmp_path / "OFERTAS DA ECONOMIA NOVA.pptx"
    fake_pptx.write_bytes(b"synthetic-pptx")
    library = ImageLibrary(tmp_path / "images")
    corpus = LayoutCorpus(tmp_path / "layouts.json")
    service = CanvaTrainingService(library, corpus, tmp_path / "training")
    monkeypatch.setattr(service.importer, "import_file", lambda *_args, **_kwargs: PptxImportResult(slides=[slide]))
    result = service.train_many([fake_pptx])
    assert result.files == 1
    assert result.slides == 1
    assert result.cards == 1
    assert result.images_learned == 1
    assert result.images_accepted == 1
    assert library.stats()["products"] == 1
    assert corpus.stats()["profiles"] == 1


def test_imported_canva_card_uses_transparent_learned_style():
    registry = ProductCardRegistry()
    product = Product(original_name="ARROZ 5KG", price="15,21", unit="UN")
    card = ProductCard(
        product_id=product.id,
        overrides={
            "imported_from_canva": True,
            "imported_style": {
                "image_region": {"x": 0.05, "y": 0.05, "width": 0.55, "height": 0.55},
                "name_region": {"x": 0.04, "y": 0.62, "width": 0.82, "height": 0.12},
                "price_region": {"x": 0.04, "y": 0.74, "width": 0.62, "height": 0.22},
                "name_style": {"font_name": "Anton", "fill": "#105594"},
                "price_style": {"font_name": "Anton", "fill": "#105594"},
                "image_fit": "cover",
            },
        },
    )
    vm = registry.view_model(card, product)
    assert vm.style.metadata["transparent_background"] is True
    assert vm.style.metadata["name_style"]["font_name"] == "Anton"
    assert vm.style.image_fit == "cover"
    assert vm.style.text_color == "#105594"
