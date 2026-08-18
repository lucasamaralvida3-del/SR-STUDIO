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


def test_exact_lookup_returns_best_and_alternatives():
    lib = Library([
        Asset("a", "ARROZ PATOSUL 5KG", "ARROZ PATOSUL 5KG", preferred=True),
        Asset("b", "ARROZ PATOSUL 5KG", "ARROZ PATOSUL 5KG", confidence=.88),
    ])
    result = ProductImageLookupService(lib).find_image("ARROZ PATOSUL 5KG")
    assert result.best_match.asset.id == "a"
    assert result.alternatives[0].asset.id == "b"
    assert result.confidence >= .99


def test_lookup_handles_category_prefix_alias_style_name():
    lib = Library([Asset("m", "ENERGETICO MONSTER 473ML", "ENERGÉTICO MONSTER 473ML")])
    result = ProductImageLookupService(lib).find_image("MONSTER 473ML")
    assert result.best_match is not None
    assert result.best_match.asset.id == "m"


def test_weight_mismatch_is_not_returned():
    lib = Library([
        Asset("370", "ACHOCOLATADO TODDY 370G", "TODDY 370G"),
        Asset("750", "ACHOCOLATADO TODDY 750G", "TODDY 750G"),
    ])
    result = ProductImageLookupService(lib).find_image("TODDY 370G")
    assert result.best_match.asset.id == "370"
    assert all(item.asset.id != "750" for item in result.alternatives)


def test_pending_assets_are_never_candidates():
    lib = Library([Asset("x", "LEITE TRIANGULO 1L", "LEITE TRIANGULO 1L", review_status="pending")])
    result = ProductImageLookupService(lib).find_image("LEITE TRIANGULO 1L")
    assert result.best_match is None
