from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from srstudio.core.models import Product
from srstudio.posters import PosterKind, SRPosterEngine
from srstudio.posters.importers import PromotionWorkbookImporter, WholesaleReportImporter


def test_legacy_wholesale_payload_matches_stable_text_and_total():
    product = Product(
        original_name="CERVEJA AMSTEL LATA 350ML",
        retail_price="3,99",
        wholesale_price="3,18",
        quantity="12",
        unit="À LATA",
    )
    data = SRPosterEngine().wholesale(product)
    fields = data.fields()
    assert fields["varejo"] == "3,99"
    assert fields["atacado"] == "3,18"
    assert fields["total"] == "38,16"
    assert fields["quantidade_texto"] == "12 LATAS SAEM A:"
    assert fields["quantidade_2_texto"] == "NA COMPRA A PARTIR DE 12 LATAS, O PREÇO À LATA SAI POR APENAS:"


def test_legacy_wholesale_quantity_text_for_kg_and_bottle():
    engine = SRPosterEngine()
    kg = engine.wholesale(
        Product(original_name="CARNE BOVINA", retail_price="39,90", wholesale_price="34,90", quantity="5,000", unit="KG")
    )
    bottle = engine.wholesale(
        Product(
            original_name="REFRIGERANTE GARRAFA 2L",
            retail_price="8,99",
            wholesale_price="7,49",
            quantity="6",
            unit="À GARRAFA",
        )
    )
    assert kg.fields()["quantidade_texto"] == "5,000 KG SAI A:"
    assert kg.fields()["quantidade_2_texto"] == "NA COMPRA A PARTIR DE 5,000 KG O KG SAI POR APENAS:"
    assert bottle.fields()["quantidade_texto"] == "6 GARRAFAS SAEM A:"
    assert bottle.fields()["quantidade_2_texto"] == (
        "NA COMPRA A PARTIR DE 6 GARRAFAS, O PREÇO À GARRAFA SAI POR APENAS:"
    )


def test_club_exclusive_is_valid_without_regular_promotion_price():
    product = Product(
        original_name="CAFÉ SR 500G",
        price="17,90",
        unit="UN",
        metadata={"promotion_type": 3},
    )
    engine = SRPosterEngine()
    data = engine.promotion(product, "")
    assert data.main_price is None
    assert str(data.club_price) == "17.90"
    assert data.campaign == "CLUBE EXCLUSIVO"
    assert not [issue for issue in engine.validate(data) if issue.severity == "error"]


def _promotion_workbook(path: Path) -> None:
    workbook = Workbook()
    ws = workbook.active
    ws.title = "PROMO"
    ws.append(["TERÇA VERDE 15 A 16/08/2026"])
    ws.append(["PRODUTO", "EAN", "VENDA", "PROMOÇÃO", "CLUBE", "ENTRADA", "LIMITE"])
    ws.append(["MAÇÃ NACIONAL", "100", "8,99", "6,99", None, "KG", "6KG"])
    ws.append(["CERVEJA AMSTEL LATA 350ML", "101", "3,79", "3,39", "3,18", "LATA", "6CX"])
    ws.append(["CAFÉ SR 500G", "102", "19,90", None, "17,90", "UN", None])
    workbook.save(path)


def test_promotion_workbook_restores_three_legacy_poster_types(tmp_path: Path):
    path = tmp_path / "PROMOCAO 15-08-2026.xlsx"
    _promotion_workbook(path)
    result = PromotionWorkbookImporter().import_file(path)
    assert not result.errors
    assert len(result.products) == 3
    assert [product.metadata["promotion_type"] for product in result.products] == [1, 2, 3]
    assert result.products[0].unit == "KG"
    assert result.products[1].unit == "À LATA"
    assert result.products[1].cpf_limit == "6CX"
    assert result.products[2].campaign == "CLUBE EXCLUSIVO"
    assert result.campaigns[0]["one_price"] == 1
    assert result.campaigns[0]["two_prices"] == 1
    assert result.campaigns[0]["club_only"] == 1


def test_atacado_782_parser_restores_quantity_unit_total(monkeypatch, tmp_path: Path):
    text = """782-Listagem de Produtos Atacarejo
Empresa: 1 - SUPERMERCADO RODRIGUES
15/08/2026 07:00:00
101 - CERVEJA AMSTEL LATA 350ML 3,99Preço Varejo:
A partir de 12 0,81 3,18
102 - CARNE BOVINA 39,90Preço Varejo:
A partir de 5,000 5,00 34,90
"""

    class FakePage:
        def extract_text(self):
            return text

    class FakeReader:
        def __init__(self, _path):
            self.pages = [FakePage()]

    import srstudio.posters.importers as module

    monkeypatch.setattr(module, "PdfReader", FakeReader)
    result = WholesaleReportImporter().import_file(tmp_path / "782.pdf")
    assert not result.errors
    assert len(result.products) == 2
    beer, meat = result.products
    assert beer.unit == "À LATA"
    assert beer.quantity == "12"
    assert beer.metadata["total"] == "38,16"
    assert meat.unit == "KG"
    assert meat.quantity == "5,000"
    assert meat.metadata["total"] == "174,50"
    assert result.metadata["company_name"] == "SUPERMERCADO RODRIGUES"


def test_promotion_and_wholesale_remain_dedicated_kinds():
    assert PosterKind.PROMOTION.value == "promotion"
    assert PosterKind.WHOLESALE.value == "wholesale"
