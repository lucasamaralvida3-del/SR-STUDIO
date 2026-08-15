from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from srstudio.core.models import StudioProject
from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.reader import PptxImporter


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def make_pptx(path: Path, tmp_path: Path) -> None:
    png = tmp_path / "product.png"
    Image.new("RGBA", (600, 600), (255, 255, 255, 0)).save(png)
    presentation = f'<p:presentation xmlns:p="{P}"><p:sldSz cx="10800000" cy="13500000"/></p:presentation>'
    slide = f'''<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>
    <p:sp><p:nvSpPr><p:cNvPr id="2" name="Nome"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1000000" y="7000000"/><a:ext cx="5000000" cy="1000000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:t>CAFE TESTE 500G</a:t></a:r></a:p></p:txBody></p:sp>
    <p:sp><p:nvSpPr><p:cNvPr id="3" name="Preco"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1800000" y="8500000"/><a:ext cx="3000000" cy="1500000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:t>R$ 9,99</a:t></a:r></a:p></p:txBody></p:sp>
    <p:pic><p:nvPicPr><p:cNvPr id="4" name="Produto"/></p:nvPicPr><p:blipFill><a:blip r:embed="rId1"/></p:blipFill><p:spPr><a:xfrm><a:off x="1500000" y="1500000"/><a:ext cx="5000000" cy="5000000"/></a:xfrm></p:spPr></p:pic>
    </p:spTree></p:cSld></p:sld>'''
    rels = f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Target="../media/image1.png" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"/></Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/slides/slide1.xml", slide)
        archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
        archive.write(png, "ppt/media/image1.png")


def test_pptx_reader_extracts_dimensions_and_media(tmp_path: Path) -> None:
    path = tmp_path / "canva.pptx"
    make_pptx(path, tmp_path)
    media = tmp_path / "media"
    result = PptxImporter().import_file(path, media_dir=media)
    assert len(result.slides) == 1
    slide = result.slides[0]
    assert slide.width == 10800000
    assert slide.height == 13500000
    images = [item for item in slide.elements if item.kind == "image"]
    assert len(images) == 1
    assert Path(images[0].media_path).exists()


def test_unified_pipeline_creates_product_card_from_pptx(tmp_path: Path) -> None:
    path = tmp_path / "canva.pptx"
    make_pptx(path, tmp_path)
    project = StudioProject()
    summary = UnifiedImportPipeline().import_file(path, project)
    assert summary.products_added == 1
    assert summary.cards_added == 1
    assert project.products[0].name == "CAFE TESTE 500G"
    assert str(project.products[0].price) == "9.99"
    assert Path(project.products[0].image_path).exists()
    assert project.pages[0].cards
