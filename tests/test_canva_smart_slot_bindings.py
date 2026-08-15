from __future__ import annotations

from decimal import Decimal

from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.reader import PptxElement
from srstudio.importers.pptx.semantic import PriceCluster, SemanticCard


def test_candidate_slot_bindings_tag_name_image_and_split_prices():
    name = PptxElement("text", text="ARROZ 5KG")
    image = PptxElement("image", media_path="product.png")
    currency = PptxElement("text", text="R$")
    integer = PptxElement("text", text="24")
    cents = PptxElement("text", text=",90")
    unit = PptxElement("text", text="/UN")
    app_integer = PptxElement("text", text="23")
    app_cents = PptxElement("text", text=",90")
    primary = PriceCluster(
        value=Decimal("24.90"),
        currency=currency,
        integer=integer,
        cents=cents,
        unit=unit,
        elements=[currency, integer, cents, unit],
    )
    secondary = PriceCluster(
        value=Decimal("23.90"),
        integer=app_integer,
        cents=app_cents,
        elements=[app_integer, app_cents],
    )
    candidate = SemanticCard(
        name=name,
        image=image,
        unit=unit,
        price_value=Decimal("24.90"),
        price_cluster=primary,
        secondary_price=secondary,
    )

    bindings = UnifiedImportPipeline._candidate_slot_bindings(candidate, "slot-1")

    assert bindings[id(name)] == ("slot-1", "name")
    assert bindings[id(image)] == ("slot-1", "image")
    assert bindings[id(currency)] == ("slot-1", "price_currency")
    assert bindings[id(integer)] == ("slot-1", "price_integer")
    assert bindings[id(cents)] == ("slot-1", "price_cents")
    assert bindings[id(unit)] == ("slot-1", "unit")
    assert bindings[id(app_integer)] == ("slot-1", "app_price_integer")
    assert bindings[id(app_cents)] == ("slot-1", "app_price_cents")
