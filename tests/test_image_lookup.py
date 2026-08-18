from dataclasses import dataclass, field

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
    mode: str = "RGB"
    metadata: dict = field(default_factory=dict)


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
    assert result.match_type == "exact-name"


def test_lookup_handles_category_prefix_alias_style_name():
    lib = Library([Asset("m", "ENERGETICO MONSTER 473ML", "ENERGÉTICO MONSTER 473ML")])
    result = ProductImageLookupService(lib).find_image("MONSTER 473ML")
    assert result.best_match is not None
    assert result.best_match.asset.id == "m"


def test_weight_mismatch_is_not_returned_even_when_wrong_variant_has_better_quality():
    lib = Library([
        Asset(
            "370",
            "ACHOCOLATADO TODDY 370G",
            "TODDY 370G",
            megapixels=.3,
            metadata={"quality_score": .32},
        ),
        Asset(
            "750",
            "ACHOCOLATADO TODDY 750G",
            "TODDY 750G",
            megapixels=8.0,
            metadata={"quality_score": .99},
        ),
    ])
    result = ProductImageLookupService(lib).find_image("TODDY 370G")
    assert result.best_match.asset.id == "370"
    assert all(item.asset.id != "750" for item in result.alternatives)


def test_higher_quality_breaks_tie_between_same_product_variants():
    lib = Library([
        Asset("low", "DETERGENTE YPE 500ML", "DETERGENTE YPE 500ML", metadata={"quality_score": .42}),
        Asset("high", "DETERGENTE YPE 500ML", "DETERGENTE YPE 500ML", metadata={"quality_score": .91}),
    ])
    result = ProductImageLookupService(lib).find_image("DETERGENTE YPE 500ML")
    assert result.best_match.asset.id == "high"
    assert result.quality_score == .91


def test_manual_preferred_remains_first_among_same_identity_variants():
    lib = Library([
        Asset(
            "preferred",
            "ARROZ PATOSUL 5KG",
            "ARROZ PATOSUL 5KG",
            preferred=True,
            metadata={"quality_score": .55},
        ),
        Asset("pretty", "ARROZ PATOSUL 5KG", "ARROZ PATOSUL 5KG", metadata={"quality_score": .98}),
    ])
    result = ProductImageLookupService(lib).find_image("ARROZ PATOSUL 5KG")
    assert result.best_match.asset.id == "preferred"


def test_provenance_is_returned_without_loading_image_pixels():
    provenance = {
        "source_kind": "archive-pptx",
        "source_archive": "Downloads(1).zip",
        "source_member": "OFERTAS FIM DE SEMANA NOVA.pptx",
    }
    lib = Library([
        Asset(
            "a",
            "ARROZ PATOSUL 5KG",
            "ARROZ PATOSUL 5KG",
            metadata={"quality_score": .8, "source_provenance": [provenance]},
        )
    ])
    result = ProductImageLookupService(lib).find_image("ARROZ PATOSUL 5KG")
    assert result.provenance == (provenance,)
    assert result.best_match.provenance == (provenance,)


def test_pending_assets_are_never_candidates():
    lib = Library([Asset("x", "LEITE TRIANGULO 1L", "LEITE TRIANGULO 1L", review_status="pending")])
    result = ProductImageLookupService(lib).find_image("LEITE TRIANGULO 1L")
    assert result.best_match is None
