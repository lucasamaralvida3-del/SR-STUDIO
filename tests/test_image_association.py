from srstudio.images.association import (
    AssociationEvidence,
    ProductImageAssociationEngine,
    is_likely_template_asset,
    is_product_text_candidate,
    measurement_signature,
    normalize_product_name,
    product_names_compatible,
    spatial_pair_score,
)


def ev(product, sha="a" * 64, confidence=.90, source="a.pptx", slide=1):
    return AssociationEvidence(product, sha, confidence, source, slide)


def test_normalization_preserves_identity_but_normalizes_accents_and_units():
    assert normalize_product_name("  Café  Vasconcelos 500 G ") == "CAFE VASCONCELOS 500G"
    assert normalize_product_name("LEITE TRIÂNGULO 1 lt") == "LEITE TRIANGULO 1L"
    assert normalize_product_name("TODDY 1,02 KG") == "TODDY 1.02KG"


def test_different_gramatures_are_not_aliases():
    assert measurement_signature("TODDY 370G") == ("370G",)
    assert not product_names_compatible("TODDY 370G", "TODDY 750G")
    assert product_names_compatible("CAFÉ VASCONCELOS 500 G", "CAFE VASCONCELOS 500G")


def test_product_candidate_rejects_price_and_operational_text():
    assert is_product_text_candidate("CAFÉ VASCONCELOS 500G")
    assert is_product_text_candidate("MUSSARELA TRADICIONAL")
    assert not is_product_text_candidate("R$ 18,99")
    assert not is_product_text_candidate("LIMITE DE 20UN POR CLIENTE")
    assert not is_product_text_candidate("QUINTA FILÉ")


def test_cross_document_consensus_boosts_same_product():
    engine = ProductImageAssociationEngine()
    result = engine.resolve([
        ev("ARROZ PATOSUL 5KG", confidence=.88, source="a.pptx"),
        ev("ARROZ PATOSUL 5 KG", confidence=.89, source="b.pptx"),
        ev("ARROZ PATOSUL 5KG", confidence=.90, source="c.pptx"),
    ])[0]
    assert result.normalized_name == "ARROZ PATOSUL 5KG"
    assert result.distinct_source_count == 3
    assert result.source_count == 3
    assert result.consensus_ratio == 1.0
    assert result.status == "accepted"


def test_reused_asset_with_unrelated_products_becomes_decorative():
    engine = ProductImageAssociationEngine()
    rows = [
        ev("ARROZ PATOSUL 5KG", confidence=.81, source="a.pptx", slide=1),
        ev("CAFE VASCONCELOS 500G", confidence=.82, source="a.pptx", slide=2),
        ev("DETERGENTE YPE 500ML", confidence=.80, source="a.pptx", slide=3),
        ev("LEITE TRIANGULO 1L", confidence=.83, source="a.pptx", slide=4),
        ev("MONSTER 473ML", confidence=.82, source="a.pptx", slide=5),
    ]
    result = engine.resolve(rows)[0]
    assert result.status == "decorative"
    assert result.distinct_product_count == 5


def test_conflicting_product_names_are_not_silently_accepted():
    engine = ProductImageAssociationEngine()
    rows = [
        ev("TODDY 370G", confidence=.91, source="a.pptx"),
        ev("TODDY 750G", confidence=.91, source="b.pptx"),
    ]
    result = engine.resolve(rows)[0]
    assert result.status != "accepted"
    assert result.alternatives


def test_spatial_score_rewards_horizontal_overlap_and_same_group():
    base, _ = spatial_pair_score(
        (100, 100, 300, 300), (120, 430, 260, 50), slide_width=1000, slide_height=1000
    )
    grouped, _ = spatial_pair_score(
        (100, 100, 300, 300), (120, 430, 260, 50), slide_width=1000, slide_height=1000, same_group=True
    )
    assert grouped > base


def test_template_reuse_is_conservative():
    assert is_likely_template_asset(slides_with_asset=30, total_slides=60)
    assert not is_likely_template_asset(slides_with_asset=2, total_slides=4)
    assert not is_likely_template_asset(slides_with_asset=3, total_slides=20)
