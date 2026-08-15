from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

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


def test_fast_batch_wrappers_delegate_to_proven_legacy_engines():
    engines = legacy_engines_root()
    promo = (engines / "FastPromotionBatch.ps1").read_text(encoding="utf-8-sig")
    atacado = (engines / "FastAtacadoBatch.ps1").read_text(encoding="utf-8-sig")

    assert "PowerPointEngine.ps1" in promo
    assert "output_png" in promo
    assert "output_pdf" in promo
    assert "ShowWindow" in promo
    assert "TurboPromotionPreview.ps1" not in promo

    assert "AtacadoEngine" in atacado
    assert "output_png" in atacado
    assert "output_pdf" in atacado
    assert "ShowWindow" in atacado
    assert "TurboAtacadoPreview.ps1" not in atacado


def test_fast_batch_wrappers_have_valid_powershell_syntax():
    shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if shell is None:
        pytest.skip("PowerShell indisponível neste ambiente")

    for name in ("FastPromotionBatch.ps1", "FastAtacadoBatch.ps1"):
        path = legacy_engines_root() / name
        escaped = str(path).replace("'", "''")
        command = (
            "$tokens=$null;$errors=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count -gt 0){$errors | ForEach-Object { Write-Error $_.Message }; exit 1}"
        )
        completed = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout


def test_staging_fast_renders_uncached_items_in_one_batch_and_reuses_cache(tmp_path, monkeypatch):
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


def test_fast_signature_invalidates_only_changed_product(tmp_path, monkeypatch):
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


def test_per_item_fast_errors_are_retried_with_proven_renderer(tmp_path, monkeypatch):
    service = PosterStagingService(tmp_path / "cache")
    products = [_product("ARROZ 5KG", "24,90"), _product("FEIJAO 1KG", "7,99")]
    fallback_ids: list[str] = []

    def broken_fast(products_arg, kind, outputs, campaign="", *, width, height, on_progress=None):
        items = list(products_arg)
        for index, _item in enumerate(items, start=1):
            if on_progress is not None:
                on_progress("start", index, "")
                on_progress("err", index, "Office recusou o modo rápido")
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

    monkeypatch.setattr(service.renderer, "render_many_to", broken_fast)
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
        pdf = service.pdf_artifact_path(product, PosterKind.PROMOTION)
        writer = PdfWriter()
        writer.add_blank_page(width=432, height=604)
        with pdf.open("wb") as handle:
            writer.write(handle)

    monkeypatch.setattr(
        "srstudio.posters.staging.Image.open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("não deve rasterizar PDF já pronto")),
    )

    output = tmp_path / "final.pdf"
    service.promote_pdf(products, PosterKind.PROMOTION, output)
    assert output.is_file()
    assert len(PdfReader(str(output)).pages) == 2
