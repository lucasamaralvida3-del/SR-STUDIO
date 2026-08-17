from __future__ import annotations

from openpyxl import Workbook

from srstudio.core.models import Product
from srstudio.posters.importers import PromotionWorkbookImporter
from srstudio.posters.legacy import SRPosterEngine
from srstudio.posters.legacy_bridge import LegacyPosterBridge
from srstudio.posters.orthography import PosterOrthographyCorrector


def test_corrector_restores_common_supermarket_accents_and_typos():
    corrector = PosterOrthographyCorrector()

    assert corrector.correct("acucar cafe feijao linguica") == "AÇÚCAR CAFÉ FEIJÃO LINGUIÇA"
    assert corrector.correct("almondega suina com file") == "ALMÔNDEGA SUÍNA COM FILÉ"
    assert corrector.correct("abobrinnha e brocolis") == "ABOBRINHA E BRÓCOLIS"
    assert corrector.correct("agua sanitaria 2l") == "ÁGUA SANITÁRIA 2L"


def test_corrector_repairs_missing_extra_replaced_and_transposed_letters():
    corrector = PosterOrthographyCorrector()

    assert corrector.correct("refrgerante") == "REFRIGERANTE"
    assert corrector.correct("refrigerantte") == "REFRIGERANTE"
    assert corrector.correct("margarna") == "MARGARINA"
    assert corrector.correct("margairna") == "MARGARINA"
    assert corrector.correct("parbolizado tradiconal") == "PARBOILIZADO TRADICIONAL"
    assert corrector.correct("salsixa") == "SALSICHA"


def test_corrector_repairs_accidentally_split_and_joined_words():
    corrector = PosterOrthographyCorrector()

    assert corrector.correct("refri gerante coca cola 2l") == "REFRIGERANTE COCA COLA 2L"
    assert corrector.correct("leitecondensado triangulo 395g") == "LEITE CONDENSADO TRIÂNGULO 395G"


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
    assert corrector.correct("Coca Cola 2L") == "COCA COLA 2L"
    assert corrector.correct("Coca-Cola 2L") == "COCA-COLA 2L"
    assert corrector.correct("7891234567890 500g cx") == "7891234567890 500G CX"


def test_spreadsheet_import_corrects_display_name_immediately(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PROMO"
    sheet.append(["PROMOÇÃO 17/08/2026"])
    sheet.append(["PRODUTO", "PROMOÇÃO", "ENTRADA"])
    sheet.append(["refrgerante coca cola 2l", 8.99, "UNIDADE"])
    sheet.append(["leitecondensado triangulo 395g", 6.49, "UNIDADE"])
    path = tmp_path / "promocao_17-08-2026.xlsx"
    workbook.save(path)

    result = PromotionWorkbookImporter().import_file(path)

    assert not result.errors
    assert len(result.products) == 2
    first, second = result.products
    assert first.original_name == "refrgerante coca cola 2l"
    assert first.display_name == "REFRIGERANTE COCA COLA 2L"
    assert first.name == "REFRIGERANTE COCA COLA 2L"
    assert first.metadata["orthography_original"] == "refrgerante coca cola 2l"
    assert first.metadata["orthography_corrected"] == "REFRIGERANTE COCA COLA 2L"
    assert first.metadata["orthography_changed"] is True
    assert first.metadata["orthography_mode"] == "aggressive_offline_v2"
    assert second.name == "LEITE CONDENSADO TRIÂNGULO 395G"


def test_atacado_excel_source_is_also_corrected_before_entering_queue():
    product = Product(
        original_name="linguca suina tradiconal 1kg",
        source="atacado_excel",
        wholesale_price="16,90",
    )

    assert product.original_name == "linguca suina tradiconal 1kg"
    assert product.name == "LINGUIÇA SUÍNA TRADICIONAL 1KG"
    assert product.metadata["orthography_mode"] == "aggressive_offline_v2"


def test_non_poster_product_keeps_imported_display_text_untouched():
    product = Product(original_name="refrgerante coca cola 2l", source="encartes_excel")

    assert product.name == "refrgerante coca cola 2l"
    assert "orthography_mode" not in product.metadata


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
