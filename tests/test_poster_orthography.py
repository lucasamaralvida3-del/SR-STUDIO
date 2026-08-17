from __future__ import annotations

from srstudio.core.models import Product
from srstudio.posters.legacy import SRPosterEngine
from srstudio.posters.legacy_bridge import LegacyPosterBridge
from srstudio.posters.orthography import PosterOrthographyCorrector


def test_corrector_restores_common_supermarket_accents_and_typos():
    corrector = PosterOrthographyCorrector()

    assert corrector.correct("acucar cafe feijao linguica") == "AÇÚCAR CAFÉ FEIJÃO LINGUIÇA"
    assert corrector.correct("almondega suina com file") == "ALMÔNDEGA SUÍNA COM FILÉ"
    assert corrector.correct("abobrinnha e brocolis") == "ABOBRINHA E BRÓCOLIS"
    assert corrector.correct("agua sanitaria 2l") == "ÁGUA SANITÁRIA 2L"


def test_corrector_uses_context_for_ambiguous_words():
    corrector = PosterOrthographyCorrector()

    assert corrector.correct("maca do peito angus") == "MAÇÃ DO PEITO ANGUS"
    assert corrector.correct("maca nacional gala") == "MAÇÃ NACIONAL GALA"
    assert corrector.correct("leite em po 400g") == "LEITE EM PÓ 400G"
    assert corrector.correct("pe de frango") == "PÉ DE FRANGO"


def test_corrector_preserves_unknown_brands_codes_weights_and_abbreviations():
    corrector = PosterOrthographyCorrector()

    assert corrector.correct("Toddy 750g") == "TODDY 750G"
    assert corrector.correct("Qboa 2L cloro ativo") == "QBOA 2L CLORO ATIVO"
    assert corrector.correct("Franbacon 5x1") == "FRANBACON 5X1"
    assert corrector.correct("pernil s/ osso") == "PERNIL S/OSSO"


def test_engine_corrects_only_display_name_without_mutating_product():
    product = Product(original_name="CAFE MOIDO 500G", price="18,90", unit="UN")
    engine = SRPosterEngine()

    data = engine.promotion(product)

    assert data.name == "CAFÉ MOÍDO 500G"
    assert product.name == "CAFE MOIDO 500G"
    assert product.unit == "UN"


def test_promotion_powerpoint_payload_receives_corrected_name_and_cada():
    product = Product(
        original_name="ACUCAR DELTA 5KG",
        price="18,90",
        unit="UN",
        metadata={"promotion_type": 1},
    )

    job = LegacyPosterBridge()._promotion_jobs([product], "")[0]

    assert job["produto"] == "AÇÚCAR DELTA 5KG"
    assert job["unidade_exibicao"] == "CADA"
    assert product.name == "ACUCAR DELTA 5KG"


def test_wholesale_payload_also_uses_corrected_display_name():
    product = Product(
        original_name="LINGUICA SUINA 1KG",
        retail_price="18,90",
        wholesale_price="16,90",
        quantity="10",
        unit="UN",
    )

    job = LegacyPosterBridge()._wholesale_jobs([product])[0]

    assert job["nome"] == "LINGUIÇA SUÍNA 1KG"
