from srstudio.images.association import AssociationAlternative, AssociationDecision, AssociationEvidence
from srstudio.images.evidence_aliases import evidence_aliases


def decision(canonical, evidence_names, alternatives=()):
    evidence = tuple(
        AssociationEvidence(name, "a" * 64, .92, "corpus.pptx", index + 1)
        for index, name in enumerate(evidence_names)
    )
    alt = tuple(
        AssociationAlternative(name, name, 1, 1, .8)
        for name in alternatives
    )
    return AssociationDecision(
        image_sha256="a" * 64,
        product_name=canonical,
        normalized_name=canonical,
        confidence=.94,
        status="accepted",
        consensus_ratio=1.0,
        source_count=len(evidence),
        distinct_source_count=1,
        observation_count=len(evidence),
        distinct_product_count=1 + len(alt),
        alternatives=alt,
        evidence=evidence,
    )


def test_same_sku_formatting_and_accent_variants_become_aliases():
    item = decision(
        "CAFÉ VASCONCELOS 500G",
        ["CAFÉ VASCONCELOS 500G", "CAFE VASCONCELOS 500 G"],
    )
    assert evidence_aliases(item) == ("CAFE VASCONCELOS 500 G",)


def test_different_gramature_is_never_learned_as_alias():
    item = decision("TODDY 370G", ["TODDY 370G"], ["TODDY 750G"])
    assert evidence_aliases(item) == ()


def test_compatible_alternative_can_be_alias_but_unrelated_name_cannot():
    item = decision(
        "LEITE TRIÂNGULO 1L",
        ["LEITE TRIÂNGULO 1L"],
        ["LEITE TRIANGULO 1 LT", "CAFÉ TRIANGULO 500G"],
    )
    assert evidence_aliases(item) == ("LEITE TRIANGULO 1 LT",)
