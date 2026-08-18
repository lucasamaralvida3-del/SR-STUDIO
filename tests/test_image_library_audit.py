from dataclasses import dataclass, field

from srstudio.images.library_audit import audit_library, payload


@dataclass
class Asset:
    id: str
    product_key: str = ""
    product_name: str = ""
    aliases: tuple[str, ...] = ()
    kind: str = "product"
    review_status: str = "accepted"
    preferred: bool = False
    confidence: float = .95
    usage_count: int = 0
    megapixels: float = 1.0
    source: str = ""
    metadata: dict = field(default_factory=dict)


class Library:
    index_path = None

    def __init__(self, assets):
        self.assets = list(assets)

    def all(self, *, status="", kind=""):
        rows = list(self.assets)
        if status:
            rows = [row for row in rows if row.review_status == status]
        if kind:
            rows = [row for row in rows if row.kind == kind or (kind == "product" and not row.kind and bool(row.product_key or row.product_name))]
        return rows


def test_aliases_cover_catalog_spellings_without_inflating_canonical_product_count():
    library = Library(
        [
            Asset(
                "img-1",
                product_key="CAFE VASCONCELOS 500G",
                product_name="Café Vasconcelos 500 G",
                aliases=("CAFE VASCONCELOS PCT 500G",),
            )
        ]
    )

    audit = audit_library(
        library,
        ["CAFE VASCONCELOS 500G", "CAFE VASCONCELOS PCT 500G"],
    )

    assert audit.metrics.accepted_products == 1
    assert audit.metrics.catalog_products == 2
    assert audit.metrics.catalog_products_with_accepted_image == 2
    assert audit.metrics.catalog_products_without_accepted_image == 0


def test_legacy_asset_with_product_name_is_product_even_when_kind_is_blank():
    audit = audit_library(
        Library([Asset("legacy", product_name="MONSTER 473ML", kind="")]),
        ["MONSTER 473ML"],
    )

    assert audit.metrics.product_assets == 1
    assert audit.metrics.unknown_assets == 0
    assert audit.metrics.images_without_product == 0
    assert audit.metrics.accepted_products == 1


def test_decorative_assets_do_not_count_as_unassigned_product_images():
    decorative = Asset(
        "decor",
        kind="",
        product_name="",
        review_status="pending",
        metadata={"association_status": "decorative", "match_reason": "template-reuse"},
    )
    unknown = Asset("unknown", kind="", product_name="", review_status="pending")

    audit = audit_library(Library([decorative, unknown]))

    assert audit.metrics.decorative_assets == 1
    assert audit.metrics.unknown_assets == 1
    assert audit.metrics.images_without_product == 1


def test_provenance_and_variant_counts_measure_observations_without_copying_pixels():
    asset = Asset(
        "img",
        product_name="DETERGENTE YPE 500ML",
        source="canva",
        metadata={
            "variant_sha256": ["a" * 64, "b" * 64],
            "provenance": [
                {"source_kind": "canva", "source_file": "a.pptx"},
                {"source_kind": "standalone-library", "source_file": "product.png"},
            ],
        },
    )
    manual = Asset("manual", product_name="MONSTER 473ML", source="manual")

    audit = audit_library(Library([asset, manual]))

    assert audit.metrics.canonical_assets == 2
    assert audit.metrics.raw_observations == 3
    assert audit.metrics.visual_variant_hashes == 2
    assert dict(audit.source_kinds) == {
        "canva": 1,
        "standalone-library": 1,
        "manual": 1,
    }


def test_pending_and_rejected_are_separated_and_missing_catalog_products_are_reported():
    pending = Asset(
        "pending",
        product_name="TODDY 370G",
        review_status="pending",
        metadata={"review_reason": "same_image_multiple_products"},
    )
    rejected = Asset(
        "rejected",
        product_name="TODDY 750G",
        review_status="rejected",
    )
    accepted = Asset("accepted", product_name="MONSTER 473ML", review_status="accepted")

    audit = audit_library(
        Library([pending, rejected, accepted]),
        ["TODDY 370G", "TODDY 750G", "MONSTER 473ML", "LEITE TRIANGULO 1L"],
    )

    assert audit.metrics.accepted_assets == 1
    assert audit.metrics.pending_assets == 1
    assert audit.metrics.rejected_assets == 1
    assert audit.metrics.accepted_products == 1
    assert audit.metrics.pending_products == 1
    assert audit.pending_product_names == ("TODDY 370G",)
    assert dict(audit.review_reasons) == {"same_image_multiple_products": 1}
    assert set(audit.products_without_image) == {
        "TODDY 370G",
        "TODDY 750G",
        "LEITE TRIANGULO 1L",
    }


def test_query_audit_uses_only_accepted_lookup_candidates():
    library = Library(
        [
            Asset("accepted", product_name="MONSTER 473ML", review_status="accepted", confidence=.96),
            Asset("pending", product_name="TODDY 370G", review_status="pending", confidence=.99),
        ]
    )

    audit = audit_library(library, queries=["MONSTER 473ML", "TODDY 370G", "INEXISTENTE 1KG"])
    rows = {row["query"]: row for row in audit.queries}

    assert rows["MONSTER 473ML"]["found"] is True
    assert rows["MONSTER 473ML"]["best_image_id"] == "accepted"
    assert rows["TODDY 370G"]["found"] is False
    assert rows["INEXISTENTE 1KG"]["found"] is False


def test_payload_is_json_ready_and_preserves_metrics():
    audit = audit_library(
        Library([Asset("accepted", product_name="MONSTER 473ML")]),
        ["MONSTER 473ML", "DETERGENTE YPE 500ML"],
    )

    data = payload(audit)

    assert data["metrics"]["accepted_products"] == 1
    assert data["metrics"]["catalog_products_without_accepted_image"] == 1
    assert data["products_without_image"] == ["DETERGENTE YPE 500ML"]
