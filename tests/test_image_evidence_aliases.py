from types import SimpleNamespace

from srstudio.images.association import AssociationAlternative, AssociationDecision, AssociationEvidence
from srstudio.images.evidence_aliases import apply_evidence_aliases, evidence_aliases


def decision(canonical, evidence_names, alternatives=(), sha="a" * 64):
    evidence = tuple(
        AssociationEvidence(name, sha, .92, "corpus.pptx", index + 1)
        for index, name in enumerate(evidence_names)
    )
    alt = tuple(
        AssociationAlternative(name, name, 1, 1, .8)
        for name in alternatives
    )
    return AssociationDecision(
        image_sha256=sha,
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


class FakeLibrary:
    def __init__(self, asset):
        self.asset = asset
        self.updates = []

    def find_for_product(self, product_name):
        return [self.asset]

    def update_metadata(self, asset_id, **changes):
        self.updates.append((asset_id, changes))
        self.asset.aliases = tuple(changes.get("aliases", self.asset.aliases))
        return self.asset


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


def test_alias_learning_accepts_evidence_from_known_visual_variant():
    canonical_sha = "a" * 64
    variant_sha = "b" * 64
    asset = SimpleNamespace(
        id="asset-1",
        aliases=(),
        metadata={"sha256": canonical_sha, "variant_sha256": [variant_sha]},
    )
    library = FakeLibrary(asset)
    item = decision(
        "CAFÉ VASCONCELOS 500G",
        ["CAFÉ VASCONCELOS 500G", "CAFE VASCONCELOS 500 G"],
        sha=variant_sha,
    )

    stats = apply_evidence_aliases(library, [item])

    assert stats.aliases_added == 1
    assert library.updates
    assert asset.aliases == ("CAFE VASCONCELOS 500 G",)


def test_alias_learning_rejects_unrelated_image_sha():
    asset = SimpleNamespace(
        id="asset-1",
        aliases=(),
        metadata={"sha256": "a" * 64, "variant_sha256": ["b" * 64]},
    )
    library = FakeLibrary(asset)
    item = decision(
        "CAFÉ VASCONCELOS 500G",
        ["CAFÉ VASCONCELOS 500G", "CAFE VASCONCELOS 500 G"],
        sha="c" * 64,
    )

    stats = apply_evidence_aliases(library, [item])

    assert stats.aliases_added == 0
    assert library.updates == []
