from __future__ import annotations

from pathlib import Path

from PIL import Image

from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.legacy_bridge import legacy_engines_root
from srstudio.posters.staging import PosterStagingService, StagedPoster


def _product(name: str, price: str) -> Product:
    return Product(
        original_name=name,
        price=price,
        campaign="OFERTA!!",
        metadata={"promotion_type": 1},
    )


def test_turbo_engines_use_one_powerpoint_session_with_safe_model_open_per_item():
    promo = (legacy_engines_root() / "TurboPromotionPreview.ps1").read_text(encoding="utf-8-sig")
    atacado = (legacy_engines_root() / "TurboAtacadoPreview.ps1").read_text(encoding="utf-8-sig")
    assert "[Activator]::CreateInstance" in promo
    assert "$ppt.Presentations.Open" in promo
    assert "$sourceSlide.Duplicate()" not in promo
    assert "BATCH_DONE" in promo
    assert "[Activator]::CreateInstance" in atacado
    assert "$ppt.Presentations.Open" in atacado
    assert "$sourceSlide.Duplicate()" not in atacado
    assert "BATCH_DONE" in atacado


def test_staging_turbo_renders_uncached_items_in_one_batch_and_reuses_cache(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    products = [_product("ARROZ 5KG", "24,90"), _product("FEIJAO 1KG", "7,99")]
    calls: list[list[str]] = []

    def fake_render_many(products_arg, kind, outputs, campaign="", *, width, height, on_progress=None):
        items = list(products_arg)
        calls.append([item.id for item in items])
        for index, item in enumerate(items, start=1):
            if on_progress is not None:
                on_progress("start", index, "")
            path = Path(outputs[item.id])
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (width, height), "white").save(path, "PNG")
            if on_progress is not None:
                on_progress("ok", index, str(path))
        return {item.id: Path(outputs[item.id]) for item in items}

    monkeypatch.setattr(service.renderer, "render_many_to", fake_render_many)
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
    assert sum(1 for event in events if event[0] == "done") == 2

    events.clear()
    second = service.stage_many_turbo(products, PosterKind.PROMOTION)
    assert len(calls) == 1, "cache válido não deve abrir PowerPoint novamente"
    assert second.generated == 0
    assert second.reused == 2
    assert second.failed == 0


def test_turbo_signature_invalidates_only_changed_product(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    first = _product("ARROZ 5KG", "24,90")
    second = _product("FEIJAO 1KG", "7,99")
    calls: list[list[str]] = []

    def fake_render_many(products_arg, kind, outputs, campaign="", *, width, height, on_progress=None):
        items = list(products_arg)
        calls.append([item.id for item in items])
        for index, item in enumerate(items, start=1):
            if on_progress is not None:
                on_progress("start", index, "")
            path = Path(outputs[item.id])
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (width, height), "white").save(path, "PNG")
            if on_progress is not None:
                on_progress("ok", index, str(path))
        return {item.id: Path(outputs[item.id]) for item in items}

    monkeypatch.setattr(service.renderer, "render_many_to", fake_render_many)
    service.stage_many_turbo([first, second], PosterKind.PROMOTION)
    first.price = "23,90"
    service.stage_many_turbo([first, second], PosterKind.PROMOTION)
    assert len(calls) == 2
    assert calls[1] == [first.id]


def test_per_item_turbo_errors_are_retried_with_proven_renderer(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    products = [_product("ARROZ 5KG", "24,90"), _product("FEIJAO 1KG", "7,99")]
    fallback_ids: list[str] = []

    def broken_turbo(products_arg, kind, outputs, campaign="", *, width, height, on_progress=None):
        items = list(products_arg)
        for index, _item in enumerate(items, start=1):
            if on_progress is not None:
                on_progress("start", index, "")
                on_progress("err", index, "Office recusou operação Turbo")
        return {}

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

    monkeypatch.setattr(service.renderer, "render_many_to", broken_turbo)
    monkeypatch.setattr(service, "stage_one", proven_fallback)

    result = service.stage_many_turbo(products, PosterKind.PROMOTION)

    assert fallback_ids == [product.id for product in products]
    assert result.generated == 2
    assert result.failed == 0
    assert len(result.artifacts) == 2
    assert all(artifact.valid for artifact in result.artifacts)
