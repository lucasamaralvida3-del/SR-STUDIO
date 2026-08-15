from __future__ import annotations

from pathlib import Path

from PIL import Image

from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.legacy_bridge import legacy_engines_root
from srstudio.posters.staging import PosterStagingService


def _product(name: str, price: str) -> Product:
    return Product(
        original_name=name,
        price=price,
        campaign="OFERTA!!",
        metadata={"promotion_type": 1},
    )


def test_turbo_engines_keep_powerpoint_and_models_alive_for_batch():
    promo = (legacy_engines_root() / "TurboPromotionPreview.ps1").read_text(encoding="utf-8-sig")
    atacado = (legacy_engines_root() / "TurboAtacadoPreview.ps1").read_text(encoding="utf-8-sig")
    assert "Duplicate()" in promo
    assert "Get-OpenPresentation" in promo
    assert "BATCH_DONE" in promo
    assert "Duplicate()" in atacado
    assert "$pres = $ppt.Presentations.Open" in atacado
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
