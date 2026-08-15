from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.auto_model import PosterAutoModelResolver
from srstudio.posters.commercial import (
    PosterCommercialValidator,
    enrich_promotion_commercial_data,
    ensure_imported_snapshot,
    restore_imported_snapshot,
)
from srstudio.posters.editing import PosterProductEditor
from srstudio.posters.staging import PosterStagingService


def _product() -> Product:
    return Product(
        code="123",
        original_name="PRODUTO TESTE 1L",
        price=Decimal("9.90"),
        retail_price=Decimal("11.90"),
        unit="UN",
        metadata={"promotion_type": 1, "cost": "7.50"},
    )


def test_commercial_validator_flags_below_cost_and_club_above_promo() -> None:
    validator = PosterCommercialValidator()
    product = _product()
    product.price = Decimal("6.99")
    product.app_price = Decimal("7.49")
    product.metadata["promotion_type"] = 2
    status = validator.evaluate(product, PosterKind.PROMOTION)
    codes = {issue.code for issue in status.issues}
    assert status.overall == "ERRO"
    assert "ABAIXO_CUSTO" in codes
    assert "CLUBE_MAIOR_PROMO" in codes


def test_commercial_validator_warns_when_promotion_is_far_from_sale() -> None:
    product = _product()
    product.price = Decimal("1.00")
    status = PosterCommercialValidator().evaluate(product, PosterKind.PROMOTION)
    assert any(issue.code == "PRECO_FORA_PADRAO" for issue in status.issues)


def test_enrich_commercial_data_reads_stable_cost_alias(tmp_path: Path) -> None:
    path = tmp_path / "promocao.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PROMO"
    sheet.append(["CODIGO", "PRODUTO", "CUSTO GERENCIAL", "VENDA", "PROMOCAO", "CLUBE", "ENTRADA"])
    sheet.append([123, "PRODUTO TESTE", 7.55, 11.90, 9.90, 8.90, "UN"])
    workbook.save(path)

    product = Product(
        code="123",
        original_name="PRODUTO TESTE",
        price=Decimal("9.90"),
        app_price=Decimal("8.90"),
        retail_price=Decimal("11.90"),
        metadata={
            "promotion_type": 2,
            "source_file": str(path),
            "sheet": "PROMO",
            "source_row": 2,
        },
    )
    enrich_promotion_commercial_data(path, [product])
    assert product.metadata["cost"] == "7.55"
    assert product.metadata["imported_snapshot"]["price"] == "9.90"


def test_live_limit_edit_switches_auto_model_to_limit_variant() -> None:
    product = _product()
    editor = PosterProductEditor()
    resolver = PosterAutoModelResolver()
    before = resolver.decide(product, PosterKind.PROMOTION)
    result = editor.apply(product, PosterKind.PROMOTION, "limit", "6CX")
    after = resolver.decide(product, PosterKind.PROMOTION)
    assert result.changed
    assert before.has_limit is False
    assert after.has_limit is True
    assert after.filename.endswith("_COM_LIMITE.pptx")


def test_live_club_edit_changes_between_one_and_two_prices() -> None:
    product = _product()
    editor = PosterProductEditor()
    resolver = PosterAutoModelResolver()
    editor.apply(product, PosterKind.PROMOTION, "price2", "8,79")
    assert product.metadata["promotion_type"] == 2
    assert resolver.decide(product, PosterKind.PROMOTION).short_label == "2 PREÇOS"
    editor.apply(product, PosterKind.PROMOTION, "price2", "")
    assert product.app_price is None
    assert product.metadata["promotion_type"] == 1
    assert resolver.decide(product, PosterKind.PROMOTION).short_label == "1 PREÇO"


def test_live_only_club_edit_can_create_club_exclusive() -> None:
    product = _product()
    editor = PosterProductEditor()
    editor.apply(product, PosterKind.PROMOTION, "price1", "")
    editor.apply(product, PosterKind.PROMOTION, "price2", "7,99")
    assert product.metadata["promotion_type"] == 3
    assert product.price == Decimal("7.99")
    assert product.app_price is None
    assert PosterAutoModelResolver().decide(product, PosterKind.PROMOTION).short_label == "CLUBE EXCLUSIVO"


def test_restore_imported_values_after_live_edits() -> None:
    product = _product()
    ensure_imported_snapshot(product)
    editor = PosterProductEditor()
    editor.apply(product, PosterKind.PROMOTION, "name", "NOME ALTERADO")
    editor.apply(product, PosterKind.PROMOTION, "limit", "4UN")
    editor.apply(product, PosterKind.PROMOTION, "price2", "8,49")
    assert product.metadata["edited"] is True
    assert restore_imported_snapshot(product) is True
    assert product.name == "PRODUTO TESTE 1L"
    assert product.cpf_limit == ""
    assert product.app_price is None
    assert "edited" not in product.metadata


def test_staging_signature_ignores_ui_render_state(tmp_path: Path) -> None:
    service = PosterStagingService(tmp_path)
    product = _product()
    before = service.signature(product, PosterKind.PROMOTION)
    product.metadata["render_state"] = "RENDERIZANDO"
    product.metadata["render_error"] = "visual only"
    product.metadata["edited"] = True
    after = service.signature(product, PosterKind.PROMOTION)
    assert before == after
