from srstudio.images.association import (
    AssociationEvidence,
    ProductImageAssociationEngine,
    evidence_source_identity,
    is_likely_template_asset,
    is_product_text_candidate,
    measurement_signature,
    normalize_product_name,
    product_names_compatible,
    spatial_pair_score,
)


def ev(product, sha="a" * 64, confidence=.90, source="a.pptx", slide=1, media="", metadata=None):
    return AssociationEvidence(
        product_name=product,
        image_sha256=sha,
        confidence=confidence,
        source_file=source,
        source_slide=slide,
        media_path=media,
        metadata=metadata or {},
    )


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
    assert is_product_text_candidate("TODDY 370G")
    assert is_product_text_candidate("MONSTER 473ML")
    assert is_product_text_candidate("MAIONESE HELLMANNS 500G")
    assert is_product_text_candidate("TAPIOCA AMAFIL 500G")
    assert not is_product_text_candidate("PACOTE 500G")
    assert not is_product_text_candidate("UNIDADE 500G")
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


def test_single_source_high_confidence_cannot_auto_accept():
    engine = ProductImageAssociationEngine()
    result = engine.resolve([
        ev(
            "MONSTER 473ML",
            confidence=.99,
            source="single-page.pptx",
            metadata={"source_document_id": "single-document"},
        )
    ])[0]
    assert result.distinct_source_count == 1
    assert result.confidence >= .90
    assert result.status == "probable"


def test_two_independent_documents_can_auto_accept_same_product_image():
    engine = ProductImageAssociationEngine()
    result = engine.resolve([
        ev("MONSTER 473ML", confidence=.94, source="week-1.pptx", metadata={"source_document_id": "week-1"}),
        ev("MONSTER 473ML", confidence=.95, source="week-2.pptx", metadata={"source_document_id": "week-2"}),
    ])[0]
    assert result.distinct_source_count == 2
    assert result.status == "accepted"


def test_consensus_distinguishes_same_basename_using_document_digest_path():
    engine = ProductImageAssociationEngine()
    rows = [
        ev(
            "CAFE VASCONCELOS 500G",
            confidence=.88,
            source="encarte.pptx",
            media=f"/imports/media/{digit * 24}/image1.png",
        )
        for digit in ("1", "2", "3")
    ]
    result = engine.resolve(rows)[0]
    assert result.distinct_source_count == 3
    assert result.status == "accepted"


def test_consensus_does_not_double_count_renamed_exact_file_copies():
    digest = "a1" * 12
    engine = ProductImageAssociationEngine()
    rows = [
        ev(
            "MONSTER 473ML",
            confidence=.91,
            source=filename,
            media=f"C:/srstudio/imports/media/{digest}/image7.png",
        )
        for filename in ("encarte.pptx", "encarte copia.pptx", "encarte final.pptx")
    ]
    result = engine.resolve(rows)[0]
    assert result.source_count == 3
    assert result.distinct_source_count == 1
    assert result.status != "accepted"


def test_explicit_document_identity_overrides_media_path_and_basename():
    row = ev(
        "DETERGENTE YPE 500ML",
        source="encarte.pptx",
        media="/imports/media/111111111111111111111111/image.png",
        metadata={"source_sha256": "ABCDEF1234"},
    )
    assert evidence_source_identity(row) == "abcdef1234"


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


def test_recurring_template_with_three_unrelated_products_is_decorative():
    engine = ProductImageAssociationEngine()
    rows = [
        ev("LOMBO SUINO KG", confidence=.86, slide=1, metadata={"template_asset": True}),
        ev("BATATA BEM BRASIL CANOA 1.05KG", confidence=.86, slide=2, metadata={"template_asset": True}),
        ev("PAO DE QUEIJO CONGELADO SR 1KG", confidence=.86, slide=3, metadata={"template_asset": True}),
    ]
    result = engine.resolve(rows)[0]
    assert result.status == "decorative"
    assert result.distinct_product_count == 3


def test_recurring_template_signal_does_not_reject_same_product_consensus():
    engine = ProductImageAssociationEngine()
    rows = [
        ev(
            "CAFE VASCONCELOS 500G",
            confidence=.91,
            source=f"week-{index}.pptx",
            slide=index,
            metadata={"template_asset": True, "source_document_id": f"week-{index}"},
        )
        for index in range(1, 4)
    ]
    result = engine.resolve(rows)[0]
    assert result.status == "accepted"
    assert result.distinct_product_count == 1


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
    base, signals = spatial_pair_score(
        (100, 100, 300, 300), (120, 430, 260, 50), slide_width=1000, slide_height=1000
    )
    grouped, _ = spatial_pair_score(
        (100, 100, 300, 300), (120, 430, 260, 50), slide_width=1000, slide_height=1000, same_group=True
    )
    assert signals["horizontal_overlap"] > .8
    assert signals["vertical_nearness"] > .6
    assert grouped > base


def test_grid_pairing_prefers_same_column_adjacent_row_boundary():
    # Regression for real SR/Canva flyer grids: the product text is stacked
    # directly above/below its own photo while another product can have a
    # center that is deceptively close in the neighboring grid row/column.
    slide_width = 10800000
    slide_height = 10800000
    name = (3420000, 2140000, 2050000, 390000)
    correct_image = (3520000, 2560000, 1750000, 1880000)
    wrong_neighbor = (6150000, 1520000, 1700000, 1880000)

    correct, correct_signals = spatial_pair_score(
        correct_image, name, slide_width=slide_width, slide_height=slide_height, product_likelihood=.9
    )
    wrong, wrong_signals = spatial_pair_score(
        wrong_neighbor, name, slide_width=slide_width, slide_height=slide_height, product_likelihood=.9
    )

    assert correct_signals["x_alignment"] > wrong_signals["x_alignment"]
    assert correct_signals["vertical_nearness"] > wrong_signals["vertical_nearness"]
    assert correct > wrong


def test_template_reuse_is_conservative():
    assert is_likely_template_asset(slides_with_asset=30, total_slides=60)
    assert not is_likely_template_asset(slides_with_asset=2, total_slides=4)
    assert not is_likely_template_asset(slides_with_asset=3, total_slides=20)
