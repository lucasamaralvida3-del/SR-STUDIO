from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from PIL import Image

from srstudio.core.models import StudioProject
from srstudio.images.library import ImageLibrary
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.placeholders import CanvaImagePlaceholderDetector
from srstudio.importers.pptx.reader import PptxElement, PptxImportResult, PptxSlide
from srstudio.importers.pptx.semantic import PriceCluster, SemanticCard
from srstudio.importers.pptx.slot_validation import SmartSlotValidator


def _slide() -> PptxSlide:
    name = PptxElement(
        "text",
        120,
        315,
        310,
        45,
        "CARNE DE SERENO",
        metadata={"font_name": "Anton", "font_size_pt": 18.0, "text_fill": "#FFFFFF", "align": "ctr", "z_index": 20},
    )
    placeholder = PptxElement(
        "shape",
        110,
        360,
        300,
        250,
        metadata={"fill": "#FFFFFF", "z_index": 21},
    )
    currency = PptxElement("text", 145, 510, 34, 42, "R$", metadata={"font_name": "Anton", "font_size_pt": 23.0, "text_fill": "#FFFFFF", "align": "ctr", "z_index": 30})
    integer = PptxElement("text", 185, 490, 100, 95, "42", metadata={"font_name": "Anton", "font_size_pt": 54.0, "text_fill": "#FFFFFF", "align": "ctr", "z_index": 31})
    cents = PptxElement("text", 288, 500, 52, 42, ",66", metadata={"font_name": "Anton", "font_size_pt": 19.0, "text_fill": "#FFFFFF", "align": "ctr", "z_index": 32})
    unit = PptxElement("text", 342, 535, 45, 30, "KG", metadata={"font_name": "Anton", "font_size_pt": 14.0, "text_fill": "#FFFFFF", "align": "ctr", "z_index": 33})
    return PptxSlide(index=1, width=1000, height=1250, elements=[name, placeholder, currency, integer, cents, unit])


def test_placeholder_detector_uses_only_free_area_above_price():
    slide = _slide()
    name, placeholder, currency, integer, cents, unit = slide.elements
    cluster = PriceCluster(
        value=Decimal("42.66"),
        currency=currency,
        integer=integer,
        cents=cents,
        unit=unit,
        elements=[currency, integer, cents, unit],
    )
    candidate = SemanticCard(
        name=name,
        price=integer,
        unit=unit,
        price_value=Decimal("42.66"),
        price_cluster=cluster,
        confidence=0.95,
        bounds=(120, 315, 387, 585),
    )
    found = CanvaImagePlaceholderDetector.find(candidate, slide)
    assert found is placeholder
    box = CanvaImagePlaceholderDetector.image_box(placeholder, candidate, slide)
    assert box is not None
    left, top, right, bottom = box
    assert left > placeholder.x
    assert right < placeholder.x + placeholder.width
    assert top >= placeholder.y
    assert bottom < integer.y


def test_tiny_logo_is_not_bound_as_product_image():
    slide = _slide()
    name, _placeholder, currency, integer, cents, unit = slide.elements
    tiny_logo = PptxElement("image", 235, 390, 28, 18, media_path="logo.png", metadata={"z_index": 22})
    slide.elements.append(tiny_logo)
    cluster = PriceCluster(
        value=Decimal("42.66"),
        currency=currency,
        integer=integer,
        cents=cents,
        unit=unit,
        elements=[currency, integer, cents, unit],
    )
    candidate = SemanticCard(
        name=name,
        image=tiny_logo,
        price=integer,
        unit=unit,
        price_value=Decimal("42.66"),
        price_cluster=cluster,
        confidence=0.95,
    )
    accepted, _stats = SmartSlotValidator.select([candidate], slide)
    assert accepted
    assert accepted[0].image is None


def test_pipeline_recovers_approved_bank_image_and_preserves_white_text(tmp_path, monkeypatch):
    image_path = tmp_path / "carne.png"
    Image.new("RGBA", (400, 400), (130, 30, 25, 255)).save(image_path)
    library = ImageLibrary(tmp_path / "images")
    asset = library.learn_product_image(image_path, "CARNE DE SERENO", confidence=0.96)
    assert asset.review_status == "accepted"

    source = tmp_path / "quinta-file.pptx"
    source.write_bytes(b"synthetic")
    pipeline = UnifiedImportPipeline(library)
    monkeypatch.setattr(pipeline.pptx_importer, "import_file", lambda *_args, **_kwargs: PptxImportResult(slides=[_slide()]))

    project = StudioProject()
    summary = pipeline.import_file(source, project)

    assert summary.products_added == 1
    assert summary.images_matched == 1
    assert project.products[0].image_path == asset.path
    page = project.pages[0]
    image_slots = [element for element in page.elements if element.get("slot_role") == "image"]
    assert len(image_slots) == 1
    assert image_slots[0]["synthetic_canva_image_slot"] is True
    assert image_slots[0]["path"] == asset.path
    assert image_slots[0]["hidden"] is False
    name_element = next(element for element in page.elements if element.get("slot_role") == "name")
    assert name_element["fill"] == "#FFFFFF"
    assert name_element["font_name"] == "Anton"
