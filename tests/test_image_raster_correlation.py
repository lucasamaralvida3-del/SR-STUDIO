from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from srstudio.images.raster_correlation import PptxRasterCorrelator, report_payload
from srstudio.images.raster_inventory import RasterFileInventory, RasterProductCandidate


def _element(kind, text="", x=0, y=0, width=100, height=50):
    return SimpleNamespace(kind=kind, text=text, x=x, y=y, width=width, height=height)


def _slide(index, products, *, with_image=False):
    elements = []
    for offset, product in enumerate(products):
        elements.append(_element("text", product, 100 + offset * 300, 400, 240, 60))
        elements.append(_element("text", "R$ 9,99", 120 + offset * 300, 500, 120, 50))
    if with_image:
        elements.append(_element("image", x=100, y=100, width=220, height=250))
    return SimpleNamespace(index=index, width=1000, height=1000, elements=elements)


class FakeImporter:
    def __init__(self, slides):
        self.slides = slides

    def import_file(self, path):
        return SimpleNamespace(slides=self.slides, warnings=[])


class FakeRasterInventory:
    def __init__(self, by_name):
        self.by_name = by_name

    def scan_file(self, path):
        rows = [
            RasterProductCandidate(name, name, .92, (10, 10, 100, 20))
            for name in self.by_name.get(Path(path).name, [])
        ]
        return RasterFileInventory(str(path), 1080, 1350, "composite-flyer", len(rows), rows, [])


def _raster(path: Path):
    Image.new("RGB", (1080, 1350), "white").save(path)
    return path


def test_raster_matches_structured_slide_by_product_names(tmp_path):
    raster = _raster(tmp_path / "1000255371.jpg")
    importer = FakeImporter([
        _slide(1, ["ARROZ PATOSUL 5KG", "DETERGENTE YPE 500ML"]),
        _slide(2, ["ASA DE FRANGO", "COSTELA RIPA", "PEITO DE FRANGO C OSSO"], with_image=True),
    ])
    inventory = FakeRasterInventory({
        raster.name: ["ASA DE FRANGO", "COSTELA RIPA", "PEITO DE FRANGO C OSSO"]
    })

    row = PptxRasterCorrelator(importer, inventory).correlate("quinta-file.pptx", [raster])[0]

    assert row.slide_index == 2
    assert row.matched_products == 3
    assert row.confidence > .7


def test_embedded_original_is_preferred_and_no_raster_crop_is_created(tmp_path):
    raster = _raster(tmp_path / "page.jpg")
    importer = FakeImporter([_slide(1, ["ARROZ PATOSUL 5KG"], with_image=True)])
    inventory = FakeRasterInventory({raster.name: ["ARROZ PATOSUL 5KG"]})

    row = PptxRasterCorrelator(importer, inventory).correlate("flyer.pptx", [raster])[0]

    assert row.source_preference == "embedded-original"
    assert row.embedded_image_elements == 1
    assert row.crop_candidates == []


def test_no_embedded_asset_produces_review_only_card_crop_with_text_flag(tmp_path):
    raster = _raster(tmp_path / "page.jpg")
    importer = FakeImporter([_slide(1, ["LEITE TRIANGULO 1L"], with_image=False)])
    inventory = FakeRasterInventory({raster.name: ["LEITE TRIANGULO 1L"]})

    row = PptxRasterCorrelator(importer, inventory).correlate("flyer.pptx", [raster])[0]

    assert row.source_preference == "raster-review-fallback"
    assert len(row.crop_candidates) == 1
    crop = row.crop_candidates[0]
    assert crop.review_status == "review"
    assert crop.contains_text_probability == 1.0
    assert crop.contains_price_probability == 1.0
    x, y, w, h = crop.crop_bbox
    assert 0 <= x < 1080 and 0 <= y < 1350
    assert w > 0 and h > 0


def test_unrelated_ocr_text_does_not_force_slide_correlation(tmp_path):
    raster = _raster(tmp_path / "page.jpg")
    importer = FakeImporter([_slide(1, ["ARROZ PATOSUL 5KG"], with_image=True)])
    inventory = FakeRasterInventory({raster.name: ["SHAMPOO MARCA 400ML"]})

    row = PptxRasterCorrelator(importer, inventory).correlate("flyer.pptx", [raster])[0]

    assert row.slide_index == 0
    assert row.source_preference == "unresolved"
    assert row.crop_candidates == []


def test_report_counts_embedded_preference_and_review_fallback(tmp_path):
    first = _raster(tmp_path / "a.jpg")
    second = _raster(tmp_path / "b.jpg")
    importer = FakeImporter([
        _slide(1, ["ARROZ PATOSUL 5KG"], with_image=True),
        _slide(2, ["LEITE TRIANGULO 1L"], with_image=False),
    ])
    inventory = FakeRasterInventory({
        first.name: ["ARROZ PATOSUL 5KG"],
        second.name: ["LEITE TRIANGULO 1L"],
    })
    rows = PptxRasterCorrelator(importer, inventory).correlate("flyer.pptx", [first, second])
    metrics = report_payload(rows)["metrics"]

    assert metrics["correlated"] == 2
    assert metrics["embedded_original_preferred"] == 1
    assert metrics["raster_review_fallback"] == 1
    assert metrics["review_crop_candidates"] == 1
