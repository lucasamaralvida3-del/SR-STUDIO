from __future__ import annotations

from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.preflight import PosterBatchPreflight


def promotion(**kwargs) -> Product:
    defaults = {
        "code": "100",
        "original_name": "ARROZ TESTE 5KG",
        "price": "19,90",
        "retail_price": "22,90",
        "unit": "UN",
        "validity": "16/08 A 18/08/2026",
        "metadata": {"promotion_type": 1},
    }
    defaults.update(kwargs)
    return Product(**defaults)


def test_one_price_batch_is_ready_when_required_data_exists() -> None:
    report = PosterBatchPreflight().evaluate([promotion()], PosterKind.PROMOTION)

    assert report.ready
    assert report.critical == 0
    assert report.products == 1
    assert report.model_summary.get("1 PREÇO") == 1


def test_two_price_without_club_price_is_blocked() -> None:
    product = promotion(metadata={"promotion_type": 2}, app_price=None)

    report = PosterBatchPreflight().evaluate([product], PosterKind.PROMOTION)

    assert not report.ready
    assert any(issue.code == "CLUBE_OBRIGATORIO" for issue in report.issues)


def test_render_failure_blocks_final_pdf() -> None:
    product = promotion(metadata={"promotion_type": 1, "render_state": "ERRO", "render_error": "PowerPoint falhou"})

    report = PosterBatchPreflight().evaluate([product], PosterKind.PROMOTION)

    assert not report.ready
    assert any(issue.code == "RENDER_ERRO" for issue in report.issues)


def test_duplicate_products_are_reported_as_attention() -> None:
    left = promotion(code="200", original_name="CAFE TESTE 500G")
    right = promotion(code="200", original_name="CAFE TESTE 500G", price="18,90")

    report = PosterBatchPreflight().evaluate([left, right], PosterKind.PROMOTION)

    assert report.ready
    assert report.warnings >= 1
    assert any(issue.code == "DUPLICADO" for issue in report.issues)
