from __future__ import annotations

import base64
from pathlib import Path
import zipfile

import pytest

from srstudio.graphics2.model import AssetRef, GraphicsDocument, GraphicsNode, NodeKind, Transform
from srstudio.graphics2.pptx_artwork import PptxArtworkRecoveryReport, recover_pptx_artwork
from srstudio.graphics2.pptx_fill_rect import recover_pptx_fill_rects


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PRESENTATION = (
    '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    '<p:sldSz cx="1000000" cy="1000000"/></p:presentation>'
)
RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Target="../media/image1.png" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"/>'
    '</Relationships>'
)


def _pptx(path: Path, *, name: str = "Banner Artwork", x: int = 0, y: int = 0, w: int = 1000000, h: int = 900000) -> Path:
    slide = f'''<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
 <p:cSld><p:spTree><p:nvGrpSpPr/><p:grpSpPr/>
 <p:sp><p:nvSpPr><p:cNvPr id="2" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
 <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>
 <a:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect l="-1000" t="0" r="-2000" b="0"/></a:stretch></a:blipFill>
 </p:spPr></p:sp></p:spTree></p:cSld></p:sld>'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", PRESENTATION)
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", RELS)
        archive.writestr("ppt/media/image1.png", PNG)
    return path


def _document() -> GraphicsDocument:
    document = GraphicsDocument(name="Artwork recovery")
    document.active_page.width = 100.0
    document.active_page.height = 100.0
    return document


def test_artwork_report_empty_is_ready():
    report = PptxArtworkRecoveryReport()
    assert report.coverage == 1.0
    assert report.large_artwork_coverage == 1.0


def test_recovers_missing_large_artwork(tmp_path):
    document = _document()
    report = recover_pptx_artwork(_pptx(tmp_path / "banner.pptx"), document, cache_dir=tmp_path / "cache")

    assert report.source_images == report.ready_images == 1
    assert report.source_large_artworks == report.ready_large_artworks == 1
    assert report.recovered_nodes == 1
    assert report.coverage == pytest.approx(1.0)
    node = next(iter(document.active_page.nodes.values()))
    assert node.kind is NodeKind.IMAGE
    assert node.locked and node.visible
    assert node.transform.width == pytest.approx(100.0)
    assert node.transform.height == pytest.approx(90.0)
    assert node.style["fill_rect"]["l"] == pytest.approx(-0.01)
    assert node.style["fill_rect"]["r"] == pytest.approx(-0.02)
    assert Path(document.assets[node.asset_id].source).is_file()


def test_repairs_broken_existing_artwork_asset(tmp_path):
    document = _document()
    broken = AssetRef(kind="image", source=str(tmp_path / "missing.png"))
    document.assets[broken.id] = broken
    node = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Banner Artwork",
        transform=Transform(width=100.0, height=90.0),
        asset_id=broken.id,
        metadata={"source_name": "Banner Artwork", "bound_image_source": str(tmp_path / "also-missing.png")},
    )
    document.active_page.add_node(node)

    report = recover_pptx_artwork(_pptx(tmp_path / "repair.pptx"), document, cache_dir=tmp_path / "cache")

    assert report.matched_images == 1
    assert report.repaired_assets == 1
    assert report.recovered_nodes == 0
    assert len(document.active_page.nodes) == 1
    assert Path(document.assets[node.asset_id].source).is_file()
    assert Path(node.metadata["bound_image_source"]).is_file()
    assert node.metadata["pptx_artwork_verified"] is True


def test_fill_rect_pipeline_recovers_artwork_before_exact_contract(tmp_path):
    document = _document()
    report = recover_pptx_fill_rects(_pptx(tmp_path / "pipeline.pptx"), document)

    artwork = document.metadata["pptx_artwork_recovery"]
    assert artwork["source_images"] == 1
    assert artwork["recovered_nodes"] == 1
    assert artwork["large_artwork_coverage"] == pytest.approx(1.0)
    assert report.source_contracts == report.mapped_contracts == report.exact_contracts == 1
    node = next(iter(document.active_page.nodes.values()))
    assert node.style["fill_rect"]["l"] == pytest.approx(-0.01)
    assert node.style["fill_rect"]["r"] == pytest.approx(-0.02)


def test_duplicate_names_are_not_guessed_when_geometry_is_ambiguous(tmp_path):
    document = _document()
    for index in range(2):
        document.active_page.add_node(
            GraphicsNode(
                id=f"duplicate-{index}",
                kind=NodeKind.IMAGE,
                name="Artwork repetido",
                transform=Transform(x=70.0 + index * 5.0, y=70.0, width=20.0, height=20.0),
                metadata={"source_name": "Artwork repetido"},
            )
        )
    source = _pptx(tmp_path / "ambiguous.pptx", name="Artwork repetido", x=100000, y=100000, w=500000, h=500000)

    report = recover_pptx_artwork(source, document, cache_dir=tmp_path / "cache")

    assert report.ambiguous_images == 1
    assert report.ready_images == 0
    assert report.recovered_nodes == 0
    assert any(issue.code == "PPTX_ARTWORK_AMBIGUOUS" for issue in report.issues)
