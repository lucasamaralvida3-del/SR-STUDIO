from decimal import Decimal

from srstudio.core.models import Product
from srstudio.posters.auto_model import PosterAutoModelResolver
from srstudio.posters.core import PosterKind
from srstudio.posters.legacy_bridge import LegacyPosterBridge


def _product(*, poster_type: int, limit: str = "", promo="9.99", club=None) -> Product:
    return Product(
        code="1",
        original_name="PRODUTO TESTE",
        price=Decimal(promo) if promo is not None else None,
        app_price=Decimal(club) if club is not None else None,
        unit="UN",
        cpf_limit=limit,
        validity="15/08/2026",
        campaign="OFERTA TESTE!!",
        metadata={"promotion_type": poster_type},
    )


def test_auto_model_one_price_without_limit() -> None:
    decision = PosterAutoModelResolver().promotion(_product(poster_type=1))
    assert decision.filename == "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx"
    assert decision.short_label == "1 PREÇO"
    assert decision.poster_type == 1


def test_auto_model_one_price_with_limit() -> None:
    decision = PosterAutoModelResolver().promotion(_product(poster_type=1, limit="6CX"))
    assert decision.filename == "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx"
    assert decision.short_label == "1 PREÇO + LIMITE"


def test_auto_model_two_prices_without_limit() -> None:
    decision = PosterAutoModelResolver().promotion(_product(poster_type=2, club="8.49"))
    assert decision.filename == "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx"
    assert decision.short_label == "2 PREÇOS"
    assert decision.poster_type == 2


def test_auto_model_two_prices_with_limit() -> None:
    decision = PosterAutoModelResolver().promotion(_product(poster_type=2, club="8.49", limit="4UN"))
    assert decision.filename == "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"
    assert decision.short_label == "2 PREÇOS + LIMITE"


def test_auto_model_club_only_without_limit() -> None:
    decision = PosterAutoModelResolver().promotion(_product(poster_type=3, promo="7.59"))
    assert decision.filename == "CLUBE_EXCLUSIVO.pptx"
    assert decision.short_label == "CLUBE EXCLUSIVO"
    assert decision.poster_type == 3


def test_auto_model_club_only_with_limit() -> None:
    decision = PosterAutoModelResolver().promotion(_product(poster_type=3, promo="7.59", limit="6CX"))
    assert decision.filename == "CLUBE_EXCLUSIVO_COM_LIMITE.pptx"
    assert decision.short_label == "CLUBE + LIMITE"


def test_auto_model_sale_poster_uses_cartaz_venda() -> None:
    decision = PosterAutoModelResolver().promotion(_product(poster_type=0, promo="5.50"))
    assert decision.filename == "CARTAZ_VENDA.pptx"
    assert decision.poster_type == 0


def test_auto_model_wholesale_is_atacado() -> None:
    product = Product(original_name="ARROZ 5KG", retail_price=Decimal("29.90"), wholesale_price=Decimal("26.90"))
    decision = PosterAutoModelResolver().decide(product, PosterKind.WHOLESALE)
    assert decision.filename == "ATACADO.pptx"
    assert decision.short_label == "ATACADO"


def test_legacy_jobs_keep_historical_contract_and_auto_types() -> None:
    products = [
        _product(poster_type=1),
        _product(poster_type=2, club="8.49", limit="4UN"),
        _product(poster_type=3, promo="7.59", limit="6CX"),
    ]
    jobs = LegacyPosterBridge()._promotion_jobs(products, "")
    assert [job["tipo"] for job in jobs] == [1, 2, 3]
    assert set(jobs[0]) == {
        "tipo",
        "campanha",
        "produto",
        "promocao",
        "clube",
        "validade_rotulo",
        "validade",
        "unidade_exibicao",
        "limite",
    }


def test_inference_keeps_old_projects_automatic() -> None:
    product = Product(
        original_name="CERVEJA LATA",
        price=Decimal("4.39"),
        app_price=Decimal("4.19"),
        unit="À LATA",
        cpf_limit="6CX",
    )
    decision = PosterAutoModelResolver().promotion(product)
    assert decision.filename == "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"
