from pathlib import Path

from PIL import Image

from srstudio.images.raster_inventory import (
    OcrTextLine,
    RasterOcrInventory,
    parse_tesseract_tsv,
)


class FakeProvider:
    def __init__(self, lines, *, available=True):
        self.lines = lines
        self.is_available = available

    def available(self):
        return self.is_available

    def recognize(self, image_path):
        return list(self.lines)


def _image(path: Path):
    Image.new("RGB", (1080, 1350), "white").save(path)
    return path


def test_composite_flyer_ocr_discovers_products_but_never_auto_accepts(tmp_path):
    source = _image(tmp_path / "1000255371.jpg")
    provider = FakeProvider(
        [
            OcrTextLine("MONSTER 473ML", 96.0, (100, 100, 250, 45)),
            OcrTextLine("R$ 8,99", 98.0, (110, 160, 140, 40)),
            OcrTextLine("OFERTA", 97.0, (400, 50, 120, 40)),
            OcrTextLine("DETERGENTE YPE 500ML", 94.0, (600, 700, 300, 50)),
        ]
    )

    report = RasterOcrInventory(provider).scan([source])

    assert report.metrics.files == 1
    assert report.metrics.product_candidates == 2
    assert report.metrics.unique_products == 2
    assert report.metrics.composite_flyers == 1
    item = report.files[0]
    assert item.content_mode == "composite-flyer"
    assert {row.normalized_name for row in item.product_candidates} == {
        "MONSTER 473ML",
        "DETERGENTE YPE 500ML",
    }
    assert all(row.review_status == "review" for row in item.product_candidates)
    assert all(row.confidence <= .89 for row in item.product_candidates)


def test_single_product_raster_remains_review_candidate(tmp_path):
    source = _image(tmp_path / "produto.png")
    provider = FakeProvider([OcrTextLine("CAFE VASCONCELOS 500G", 99.0, (200, 900, 500, 60))])

    report = RasterOcrInventory(provider).scan([source])

    assert report.metrics.single_product_rasters == 1
    assert report.files[0].product_candidates[0].review_status == "review"
    assert report.files[0].product_candidates[0].confidence == .89


def test_unavailable_ocr_is_warning_and_does_not_use_filename_as_product(tmp_path):
    source = _image(tmp_path / "MONSTER 473ML.jpg")
    report = RasterOcrInventory(FakeProvider([], available=False)).scan([source])

    assert report.metrics.product_candidates == 0
    assert report.metrics.unknown_rasters == 1
    assert report.files[0].warnings == ["OCR provider unavailable"]


def test_tesseract_tsv_groups_words_into_lines_and_filters_low_confidence():
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t100\t100\t80\t30\t95\tMONSTER",
            "5\t1\t1\t1\t1\t2\t190\t100\t80\t30\t92\t473ML",
            "5\t1\t1\t1\t2\t1\t100\t150\t70\t30\t10\tRUÍDO",
            "5\t1\t1\t1\t3\t1\t100\t200\t120\t30\t90\tDETERGENTE",
            "5\t1\t1\t1\t3\t2\t230\t200\t50\t30\t90\tYPE",
            "5\t1\t1\t1\t3\t3\t290\t200\t70\t30\t90\t500ML",
        ]
    )

    lines = parse_tesseract_tsv(tsv, minimum_word_confidence=40)

    assert len(lines) == 2
    assert lines[0].text == "MONSTER 473ML"
    assert lines[0].bbox == (100, 100, 170, 30)
    assert lines[1].text == "DETERGENTE YPE 500ML"
    assert lines[1].bbox == (100, 200, 260, 30)


def test_missing_raster_source_is_report_warning(tmp_path):
    report = RasterOcrInventory(FakeProvider([])).scan([tmp_path / "missing.jpg"])
    assert report.metrics.files == 0
    assert report.warnings
