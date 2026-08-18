from dataclasses import dataclass

from srstudio.images.lookup import ProductImageLookupService


@dataclass
class Asset:
    id: str
    product_key: str
    product_name: str
    aliases: tuple = ()
    kind: str = "product"
    review_status: str = "accepted"
    preferred: bool = False
    confidence: float = .92
    usage_count: int = 0
    megapixels: float = 1.0


class Library:
    index_path = None

    def __init__(self, assets):
        self.assets = assets

    def all(self, *, status="", kind=""):
        values = self.assets
        if status:
            values = [item for item in values if item.review_status == status]
        return values


def test_rare_token_index_finds_item_in_large_common_token_bank():
    assets = [
        Asset(str(index), f"PRODUTO MARCA {index} 500G", f"PRODUTO MARCA {index} 500G")
        for index in range(5000)
    ]
    service = ProductImageLookupService(Library(assets), max_fuzzy_candidates=100)

    result = service.find_image("MARCA 4321 500G")

    assert result.best_match is not None
    assert result.best_match.asset.id == "4321"
