from decimal import Decimal
from pathlib import Path

from PIL import Image

from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.preview import LegacyPosterPreviewService
from srstudio.posters.staging import PosterStagingService


def _product(price: str = "9.99", limit: str = "") -> Product:
    return Product(
        code="123",
        original_name="PRODUTO TESTE",
        price=Decimal(price),
        unit="UN",
        cpf_limit=limit,
        campaign="OFERTA TESTE!!",
        validity="15/08/2026",
        metadata={"promotion_type": 1},
    )


def _write_print_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (PosterStagingService.PRINT_WIDTH, PosterStagingService.PRINT_HEIGHT), "white").save(path)


def test_staging_signature_changes_with_commercial_data(tmp_path: Path) -> None:
    service = PosterStagingService(tmp_path)
    first = service.signature(_product("9.99"), PosterKind.PROMOTION, "")
    second = service.signature(_product("8.99"), PosterKind.PROMOTION, "")
    limited = service.signature(_product("9.99", "6CX"), PosterKind.PROMOTION, "")
    assert first != second
    assert first != limited


def test_ready_artifact_requires_final_print_resolution(tmp_path: Path) -> None:
    service = PosterStagingService(tmp_path)
    product = _product()
    path = service.artifact_path(product, PosterKind.PROMOTION)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (900, 1250), "white").save(path)
    assert service.ready_artifact(product, PosterKind.PROMOTION) is None
    _write_print_png(path)
    assert service.ready_artifact(product, PosterKind.PROMOTION) == path


def test_promote_pdf_reuses_staged_images_without_renderer(tmp_path: Path) -> None:
    service = PosterStagingService(tmp_path)
    products = [_product("9.99"), _product("8.49")]
    for product in products:
        _write_print_png(service.artifact_path(product, PosterKind.PROMOTION))

    def should_not_render(*args, **kwargs):
        raise AssertionError("renderer must not run when final-quality staging is ready")

    service.renderer.render = should_not_render  # type: ignore[method-assign]
    output = service.promote_pdf(products, PosterKind.PROMOTION, tmp_path / "final.pdf")
    assert output.is_file()
    assert output.stat().st_size > 1000


def test_silent_preview_source_can_be_promoted_to_print_resolution() -> None:
    source = '$ppt.Visible=-1\n$slide.Export($OutputPng, "PNG", 900, 1250)\n'
    rendered = LegacyPosterPreviewService._silent_script_source(source, width=1772, height=2480)
    assert "$ppt.Visible=-1" not in rendered
    assert 'Export($OutputPng, "PNG", 1772, 2480)' in rendered
