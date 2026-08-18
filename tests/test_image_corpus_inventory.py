import io
import zipfile
from pathlib import Path

from PIL import Image

from srstudio.images.corpus_inventory import PptxCorpusInventory


SLIDE = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<p:sld xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'
       xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
       xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'>
  <p:cSld><p:spTree>
    <p:sp><p:txBody><a:p><a:r><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:spPr><a:blipFill><a:blip r:embed='rId1'/></a:blipFill></p:spPr></p:sp>
  </p:spTree></p:cSld>
</p:sld>
"""

RELS = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>
  <Relationship Id='rId1'
    Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'
    Target='../media/{media_name}'/>
</Relationships>
"""


def _png_bytes(size=(320, 480), color=(220, 30, 40)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _pptx(path: Path, slides, media, extra=b""):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (text, media_name) in enumerate(slides, 1):
            archive.writestr(f"ppt/slides/slide{index}.xml", SLIDE.format(text=text))
            archive.writestr(
                f"ppt/slides/_rels/slide{index}.xml.rels",
                RELS.format(media_name=media_name),
            )
        for name, blob in media.items():
            archive.writestr(f"ppt/media/{name}", blob)
        if extra:
            archive.writestr("docProps/custom.xml", extra)
    return path


def test_inventory_reads_product_text_and_shape_fill_image(tmp_path):
    source = _pptx(
        tmp_path / "encarte.pptx",
        [("CAFÉ VASCONCELOS 500 G", "product.png")],
        {"product.png": _png_bytes()},
    )

    item = PptxCorpusInventory().scan_file(source)

    assert item.slides == 1
    assert item.raw_image_refs == 1
    assert item.media_files == 1
    assert item.unique_media_sha256 == 1
    assert item.product_text_candidates == 1
    assert item.unique_products == ["CAFE VASCONCELOS 500G"]
    assert item.content_mode == "mixed"
    assert item.media[0].width == 320
    assert item.media[0].height == 480
    assert len(item.media[0].sha256) == 64


def test_inventory_groups_exact_duplicate_files(tmp_path):
    first = _pptx(
        tmp_path / "encarte-a.pptx",
        [("MONSTER 473ML", "product.png")],
        {"product.png": _png_bytes()},
    )
    second = tmp_path / "encarte-b.pptx"
    second.write_bytes(first.read_bytes())

    report = PptxCorpusInventory().scan([first, second])

    assert report.metrics.files_found == 2
    assert report.metrics.unique_files_exact == 1
    assert report.metrics.exact_duplicate_file_groups == 1
    assert {Path(value).name for value in report.exact_duplicate_files[0]} == {
        "encarte-a.pptx",
        "encarte-b.pptx",
    }


def test_inventory_groups_logical_export_copies_despite_irrelevant_package_change(tmp_path):
    slides = [("DETERGENTE YPE 500ML", "product.png")]
    media = {"product.png": _png_bytes()}
    first = _pptx(tmp_path / "original.pptx", slides, media, extra=b"export A")
    second = _pptx(tmp_path / "export-copy.pptx", slides, media, extra=b"export B")

    report = PptxCorpusInventory().scan([first, second])

    assert report.metrics.unique_files_exact == 2
    assert report.metrics.logical_documents == 1
    assert report.metrics.logical_duplicate_groups == 1
    assert {Path(value).name for value in report.logical_duplicate_files[0]} == {
        "original.pptx",
        "export-copy.pptx",
    }


def test_three_slide_reused_media_is_template_heavy(tmp_path):
    source = _pptx(
        tmp_path / "template.pptx",
        [
            ("LOMBO SUINO 1KG", "brand.png"),
            ("BATATA BEM BRASIL 1KG", "brand.png"),
            ("PAO DE QUEIJO SR 1KG", "brand.png"),
        ],
        {"brand.png": _png_bytes()},
    )

    item = PptxCorpusInventory().scan_file(source)

    assert item.product_text_candidates == 3
    assert len(item.template_media_sha256) == 1
    assert item.content_mode == "template-heavy"


def test_dhash_collision_with_incompatible_geometry_is_reported_but_rejected_for_dedupe(tmp_path):
    square = _png_bytes((119, 119), (255, 255, 255))
    wide = _png_bytes((2160, 933), (255, 255, 255))
    source = _pptx(
        tmp_path / "collision.pptx",
        [
            ("TODDY 370G", "square.png"),
            ("TODDY 750G", "wide.png"),
        ],
        {"square.png": square, "wide.png": wide},
    )

    report = PptxCorpusInventory().scan([source])

    assert report.metrics.unique_media_exact == 2
    assert report.metrics.near_duplicate_pairs == 1
    assert report.metrics.geometry_rejected_dhash_pairs == 1
    pair = report.near_duplicate_pairs[0]
    assert pair["dhash_distance"] == 0
    assert pair["geometry_compatible"] is False


def test_missing_inventory_source_is_non_destructive_warning(tmp_path):
    report = PptxCorpusInventory().scan([tmp_path / "missing.pptx"])
    assert report.metrics.files_found == 0
    assert report.warnings
