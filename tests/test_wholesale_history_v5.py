from __future__ import annotations

from pathlib import Path

from srstudio.core.models import Product
from srstudio.posters.history import WholesaleHistoryStore


def _product(code: str, retail: str, wholesale: str, quantity: str = "6") -> Product:
    return Product(
        code=code,
        original_name=f"PRODUTO {code}",
        retail_price=retail,
        wholesale_price=wholesale,
        quantity=quantity,
        unit="UN",
        metadata={"total": "100,00"},
    )


def test_first_report_marks_products_as_new(tmp_path: Path):
    store = WholesaleHistoryStore(tmp_path / "history.sqlite3")
    source = tmp_path / "report-1.pdf"
    source.write_bytes(b"report-one")
    products = [_product("1", "10,00", "8,00"), _product("2", "20,00", "18,00")]
    summary = store.analyze_and_store(source, products, {"company_name": "SR"})
    assert summary.new == 2
    assert summary.changed == 0
    assert summary.same == 0
    assert summary.removed == 0
    assert [product.metadata["atacado_status"] for product in products] == ["NOVO", "NOVO"]


def test_second_report_detects_changed_same_removed_and_high_variation(tmp_path: Path):
    store = WholesaleHistoryStore(tmp_path / "history.sqlite3")
    first_source = tmp_path / "report-1.pdf"
    first_source.write_bytes(b"report-one")
    store.analyze_and_store(
        first_source,
        [_product("1", "10,00", "8,00"), _product("2", "20,00", "18,00"), _product("3", "30,00", "27,00")],
    )

    second_source = tmp_path / "report-2.pdf"
    second_source.write_bytes(b"report-two")
    products = [_product("1", "10,00", "4,00"), _product("2", "20,00", "18,00"), _product("4", "12,00", "10,00")]
    summary = store.analyze_and_store(second_source, products)
    lookup = {product.code: product for product in products}
    assert summary.new == 1
    assert summary.changed == 1
    assert summary.same == 1
    assert summary.removed == 1
    assert summary.removed_codes == ("3",)
    assert lookup["1"].metadata["atacado_status"] == "ALTERADO"
    assert "Atacado" in lookup["1"].metadata["atacado_reason"]
    assert "Variação alta no atacado" in lookup["1"].metadata["atacado_alert"]
    assert lookup["2"].metadata["atacado_status"] == "SEM ALTERAÇÃO"
    assert lookup["4"].metadata["atacado_status"] == "NOVO"


def test_duplicate_report_reuses_existing_history(tmp_path: Path):
    store = WholesaleHistoryStore(tmp_path / "history.sqlite3")
    source = tmp_path / "report.pdf"
    source.write_bytes(b"same-report")
    first_products = [_product("1", "10,00", "8,00")]
    first = store.analyze_and_store(source, first_products)
    second_products = [_product("1", "10,00", "8,00")]
    second = store.analyze_and_store(source, second_products)
    assert first.duplicate is False
    assert second.duplicate is True
    assert second.report_id == first.report_id
    assert second_products[0].metadata["atacado_status"] == "NOVO"


def test_report_782_absolute_discount_does_not_create_false_alert():
    product = Product(
        code="101",
        original_name="CERVEJA AMSTEL LATA 350ML",
        retail_price="3,99",
        wholesale_price="3,18",
        quantity="12",
        unit="À LATA",
        metadata={"discount": "0,81"},
    )
    assert "Desconto divergente" not in WholesaleHistoryStore.alert_for(product)


def test_report_782_inconsistent_absolute_discount_is_flagged():
    product = Product(
        code="101",
        original_name="CERVEJA AMSTEL LATA 350ML",
        retail_price="3,99",
        wholesale_price="3,18",
        quantity="12",
        unit="À LATA",
        metadata={"discount": "0,50"},
    )
    assert "Desconto divergente" in WholesaleHistoryStore.alert_for(product)
