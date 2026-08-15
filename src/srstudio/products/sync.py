from __future__ import annotations

from dataclasses import dataclass

from srstudio.core.models import StudioProject
from srstudio.products.database import ProductDatabase, ProductRecord


@dataclass(frozen=True, slots=True)
class ProductSyncResult:
    products: int
    prices_recorded: int


class ProductKnowledgeSync:
    """Alimenta o banco local a partir dos projetos sem acoplar o editor ao SQLite."""

    def __init__(self, database: ProductDatabase) -> None:
        self.database = database

    def sync_project(self, project: StudioProject, record_prices: bool = True) -> ProductSyncResult:
        records: list[ProductRecord] = []
        prices = 0
        for product in project.products:
            records.append(
                ProductRecord(
                    code=product.code,
                    ean=product.ean,
                    name=product.original_name or product.name,
                    display_name=product.display_name or product.name,
                    category=product.category,
                    unit=product.unit,
                    image_path=product.image_path,
                    last_price=str(product.price or ""),
                    metadata={
                        "source": product.source,
                        "recognition_confidence": product.recognition_confidence,
                        "validity": product.validity,
                    },
                )
            )
            if record_prices and product.price is not None:
                key = product.ean or product.code or product.name.casefold()
                self.database.record_price(key, str(product.price), project.campaign)
                prices += 1
        count = self.database.bulk_upsert(records)
        return ProductSyncResult(count, prices)
