from __future__ import annotations

from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.legacy_bridge import LegacyPosterBridge, legacy_template


def test_historical_sr_poster_assets_are_present():
    assert LegacyPosterBridge.assets_available()


def test_official_templates_are_distinct_for_promotion_and_wholesale():
    promotion = legacy_template(PosterKind.PROMOTION)
    wholesale = legacy_template(PosterKind.WHOLESALE)
    assert promotion is not None
    assert wholesale is not None
    assert promotion.metadata["legacy_engine"] == "promotion"
    assert wholesale.metadata["legacy_engine"] == "wholesale"
    assert promotion.metadata["recommended"] is True
    assert wholesale.metadata["recommended"] is True


def test_promotion_bridge_builds_legacy_three_type_payloads():
    products = [
        Product(original_name="ARROZ 5KG", price="24,90", campaign="ECONOMIA!!", metadata={"promotion_type": 1}),
        Product(
            original_name="CERVEJA AMSTEL LATA 350ML",
            price="3,39",
            app_price="3,18",
            unit="À LATA",
            cpf_limit="6CX",
            campaign="FIM DE SEMANA!!",
            metadata={"promotion_type": 2},
        ),
        Product(original_name="CAFÉ 500G", price="17,90", metadata={"promotion_type": 3}),
    ]
    jobs = LegacyPosterBridge()._promotion_jobs(products, "")
    assert [job["tipo"] for job in jobs] == [1, 2, 3]
    assert jobs[0]["promocao"] == "24,90"
    assert jobs[0]["clube"] == ""
    assert jobs[0]["unidade_exibicao"] == "CADA"
    assert jobs[1]["promocao"] == "3,39"
    assert jobs[1]["clube"] == "3,18"
    assert jobs[1]["unidade_exibicao"] == "À LATA"
    assert jobs[1]["limite"] == "6CX"
    assert jobs[2]["promocao"] == ""
    assert jobs[2]["clube"] == "17,90"
    assert jobs[2]["unidade_exibicao"] == "CADA"


def test_promotion_unit_display_keeps_business_unit_internal():
    product = Product(original_name="SABONETE 90G", price="2,99", unit="UN", metadata={"promotion_type": 1})
    job = LegacyPosterBridge()._promotion_jobs([product], "")[0]
    assert product.unit == "UN"
    assert job["unidade_exibicao"] == "CADA"


def test_promotion_unit_display_preserves_special_units():
    bridge = LegacyPosterBridge()
    assert bridge._legacy_unit("KG") == "KG"
    assert bridge._legacy_unit("À LATA") == "À LATA"
    assert bridge._legacy_unit("A LATA") == "À LATA"
    assert bridge._legacy_unit("À GARRAFA") == "À GARRAFA"
    assert bridge._legacy_unit("A GARRAFA") == "À GARRAFA"
    assert bridge._legacy_unit("UN") == "CADA"
    assert bridge._legacy_unit("") == "CADA"


def test_wholesale_bridge_payload_matches_old_engine_contract():
    product = Product(
        original_name="CERVEJA AMSTEL LATA 350ML",
        retail_price="3,99",
        wholesale_price="3,18",
        quantity="12",
        unit="À LATA",
    )
    job = LegacyPosterBridge()._wholesale_jobs([product])[0]
    assert job == {
        "nome": "CERVEJA AMSTEL LATA 350ML",
        "varejo": "3,99",
        "atacado": "3,18",
        "total": "38,16",
        "quantidade_texto": "12 LATAS SAEM A:",
        "quantidade_2_texto": "NA COMPRA A PARTIR DE 12 LATAS, O PREÇO À LATA SAI POR APENAS:",
    }
