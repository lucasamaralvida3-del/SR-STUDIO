from __future__ import annotations

from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter

from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.legacy_batch import LegacyBatchRenderResult, LegacyBatchRenderer
from srstudio.posters.staging import PosterStagingService, StagedPoster


def _product(name: str, price: str) -> Product:
    return Product(
        original_name=name,
        price=price,
        campaign="OFERTA!!",
        metadata={"promotion_type": 1},
    )


def _blank_pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=432, height=604)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def test_fast_path_calls_untouched_historical_engines_directly(tmp_path):
    renderer = LegacyBatchRenderer()
    promo_script, _ = renderer._engine_command(
        PosterKind.PROMOTION,
        tmp_path / "jobs.json",
        tmp_path / "out",
    )
    atacado_script, _ = renderer._engine_command(
        PosterKind.WHOLESALE,
        tmp_path / "jobs.json",
        tmp_path / "out",
    )
    assert promo_script.name == "PowerPointEngine.ps1"
    assert atacado_script.name == "AtacadoEngine.ps1"
    assert "FastPromotionBatch" not in str(promo_script)
    assert "TurboPromotionPreview" not in str(promo_script)
    assert "FastAtacadoBatch" not in str(atacado_script)
    assert "TurboAtacadoPreview" not in str(atacado_script)


def test_pdfium_rasterizes_official_pdf_without_powerpoint(tmp_path):
    source = _blank_pdf(tmp_path / "cartaz.pdf")
    destination = tmp_path / "cartaz.png"
    LegacyBatchRenderer.rasterize_pdf(source, destination, width=1772, height=2480)
    assert destination.is_file()
    with Image.open(destination) as image:
        assert image.size == (1772, 2480)


def test_staging_fast_renders_uncached_items_in_one_old_engine_batch_and_reuses_cache(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    products = [_product("ARROZ 5KG", "24,90"), _product("FEIJAO 1KG", "7,99")]
    calls: list[list[str]] = []

    def fake_render_pdfs(products_arg, kind, output_dir, campaign="", *, on_progress=None):
        items = list(products_arg)
        calls.append([item.id for item in items])
        result = LegacyBatchRenderResult()
        for index, item in enumerate(items, start=1):
            if on_progress is not None:
                on_progress("stage", index, "ABRINDO_MODELO")
            pdf = _blank_pdf(Path(output_dir) / f"{index:03d}_{item.name}.pdf")
            result.files[index] = pdf
            if on_progress is not None:
                on_progress("ok", index, str(pdf))
        return result

    monkeypatch.setattr(service.batch_renderer, "render_pdfs", fake_render_pdfs)
    events: list[tuple[str, int, bool, str]] = []
    first = service.stage_many_turbo(
        products,
        PosterKind.PROMOTION,
        on_progress=lambda event, index, total, product, valid, error: events.append(
            (event, index, valid, error)
        ),
    )
    assert len(calls) == 1
    assert calls[0] == [product.id for product in products]
    assert first.generated == 2
    assert first.reused == 0
    assert first.failed == 0
    assert all(artifact.valid for artifact in first.artifacts)
    assert all(service.ready_pdf_artifact(product, PosterKind.PROMOTION) for product in products)
    assert sum(1 for event in events if event[0] == "done") == 2

    second = service.stage_many_turbo(products, PosterKind.PROMOTION)
    assert len(calls) == 1, "cache válido não deve abrir PowerPoint novamente"
    assert second.generated == 0
    assert second.reused == 2
    assert second.failed == 0


def test_cached_pdf_rebuilds_missing_preview_without_opening_powerpoint(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    product = _product("ARROZ 5KG", "24,90")
    pdf = service.pdf_artifact_path(product, PosterKind.PROMOTION)
    _blank_pdf(pdf)

    monkeypatch.setattr(
        service.batch_renderer,
        "render_pdfs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("PowerPoint não deve ser chamado")),
    )
    result = service.stage_many_turbo([product], PosterKind.PROMOTION)
    assert result.reused == 1
    assert result.failed == 0
    assert service.ready_artifact(product, PosterKind.PROMOTION) is not None


def test_fast_signature_invalidates_only_changed_product(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    first = _product("ARROZ 5KG", "24,90")
    second = _product("FEIJAO 1KG", "7,99")
    calls: list[list[str]] = []

    def fake_render_pdfs(products_arg, kind, output_dir, campaign="", *, on_progress=None):
        items = list(products_arg)
        calls.append([item.id for item in items])
        result = LegacyBatchRenderResult()
        for index, item in enumerate(items, start=1):
            if on_progress is not None:
                on_progress("stage", index, "ABRINDO_MODELO")
            pdf = _blank_pdf(Path(output_dir) / f"{index:03d}_{item.name}.pdf")
            result.files[index] = pdf
            if on_progress is not None:
                on_progress("ok", index, str(pdf))
        return result

    monkeypatch.setattr(service.batch_renderer, "render_pdfs", fake_render_pdfs)
    service.stage_many_turbo([first, second], PosterKind.PROMOTION)
    first.price = "23,90"
    service.stage_many_turbo([first, second], PosterKind.PROMOTION)
    assert len(calls) == 2
    assert calls[1] == [first.id]


def test_old_engine_batch_failure_is_retried_with_proven_normal_renderer(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    products = [_product("ARROZ 5KG", "24,90"), _product("FEIJAO 1KG", "7,99")]
    fallback_ids: list[str] = []

    def broken_batch(products_arg, kind, output_dir, campaign="", *, on_progress=None):
        items = list(products_arg)
        result = LegacyBatchRenderResult(batch_error="Falha no lote antigo")
        for index, _item in enumerate(items, start=1):
            if on_progress is not None:
                on_progress("stage", index, "ABRINDO_MODELO")
                on_progress("err", index, "Falha simulada")
            result.errors[index] = "Falha simulada"
        return result

    def proven_fallback(product, kind, campaign=""):
        fallback_ids.append(product.id)
        destination = service.artifact_path(product, kind, campaign)
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (service.PRINT_WIDTH, service.PRINT_HEIGHT), "white").save(destination, "PNG")
        return StagedPoster(
            product.id,
            service.signature(product, kind, campaign),
            destination,
            service.PRINT_WIDTH,
            service.PRINT_HEIGHT,
            True,
        )

    monkeypatch.setattr(service.batch_renderer, "render_pdfs", broken_batch)
    monkeypatch.setattr(service, "stage_one", proven_fallback)

    result = service.stage_many_turbo(products, PosterKind.PROMOTION)

    assert fallback_ids == [product.id for product in products]
    assert result.generated == 2
    assert result.failed == 0
    assert len(result.artifacts) == 2
    assert all(artifact.valid for artifact in result.artifacts)


def test_final_pdf_prefers_cached_vector_pdfs(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    products = [_product("ARROZ 5KG", "24,90"), _product("FEIJAO 1KG", "7,99")]

    for product in products:
        png = service.artifact_path(product, PosterKind.PROMOTION)
        png.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (service.PRINT_WIDTH, service.PRINT_HEIGHT), "white").save(png, "PNG")
        _blank_pdf(service.pdf_artifact_path(product, PosterKind.PROMOTION))

    monkeypatch.setattr(
        "srstudio.posters.staging.Image.open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("não deve rasterizar PDF já pronto")),
    )

    output = tmp_path / "final.pdf"
    service.promote_pdf(products, PosterKind.PROMOTION, output)
    assert output.is_file()
    assert len(PdfReader(str(output)).pages) == 2
