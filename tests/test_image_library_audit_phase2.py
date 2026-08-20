from dataclasses import dataclass, field

from srstudio.images.library_audit import audit_library, coverage_payload, payload
from srstudio.images.product_priority import ProductPriorityRow


@dataclass
class Asset:
    id: str
    product_name: str = ""
    product_key: str = ""
    aliases: tuple = ()
    kind: str = "product"
    review_status: str = "accepted"
    preferred: bool = False
    confidence: float = .95
    usage_count: int = 0
    megapixels: float = 1.0
    source: str = ""
    source_file: str = ""
    path: str = ""
    metadata: dict = field(default_factory=dict)


class Library:
    index_path = None

    def __init__(self, assets):
        self.assets = list(assets)

    def all(self, *, status="", kind=""):
        rows = list(self.assets)
        if status:
            rows = [row for row in rows if row.review_status == status]
        return rows


def test_phase2_catalog_coverage_separates_accepted_likely_review_and_missing():
    library = Library([
        Asset("a", product_name="ARROZ PATOSUL 5KG", review_status="accepted"),
        Asset(
            "b",
            product_name="DETERGENTE YPE 500ML",
            review_status="pending",
            metadata={"association_status": "probable"},
        ),
        Asset(
            "c",
            product_name="MONSTER 473ML",
            review_status="pending",
            metadata={"association_status": "review"},
        ),
    ])
    catalog = [
        "ARROZ PATOSUL 5KG",
        "DETERGENTE YPE 500ML",
        "MONSTER 473ML",
        "LEITE TRIANGULO 1L",
    ]

    audit = audit_library(library, catalog)
    coverage = coverage_payload(audit.metrics)

    assert audit.metrics.catalog_auto_approved == 1
    assert audit.metrics.catalog_likely == 1
    assert audit.metrics.catalog_review_required == 1
    assert audit.metrics.catalog_without_any_image == 1
    assert audit.products_without_any_image == ("LEITE TRIANGULO 1L",)
    assert coverage["auto_approved_percent"] == 25.0
    assert coverage["without_any_image_percent"] == 25.0


def test_multiple_variants_orphans_provenance_and_low_confidence_are_audited():
    library = Library([
        Asset(
            "a",
            product_name="ARROZ PATOSUL 5KG",
            confidence=.95,
            source="canva",
            metadata={
                "variant_sha256": ["1" * 64],
                "source_provenance": [{"source_kind": "archive-pptx", "source_archive": "Downloads.zip"}],
            },
        ),
        Asset("b", product_name="ARROZ PATOSUL 5KG", confidence=.72),
        Asset("orphan", product_name="", product_key="", kind="unknown", review_status="pending"),
    ])

    audit = audit_library(library)

    assert audit.metrics.products_with_multiple_images == 1
    assert audit.products_with_multiple_images == (("ARROZ PATOSUL 5KG", 2),)
    assert audit.metrics.near_duplicate_variants == 1
    assert audit.metrics.images_without_product == 1
    assert audit.metrics.low_confidence_associations == 1
    assert dict(audit.source_kinds)["archive-pptx"] == 1


def test_top_missing_is_ranked_by_flyer_priority_and_excludes_existing_candidates():
    rows = [
        ProductPriorityRow("LEITE TRIANGULO 1L", "LEITE TRIANGULO 1L", 9, 4, True, 18.0),
        ProductPriorityRow("ARROZ PATOSUL 5KG", "ARROZ PATOSUL 5KG", 20, 5, True, 30.75),
        ProductPriorityRow("CAFE VASCONCELOS 500G", "CAFE VASCONCELOS 500G", 7, 2, True, 12.5),
    ]
    library = Library([Asset("arroz", product_name="ARROZ PATOSUL 5KG")])

    audit = audit_library(
        library,
        [row.display_name for row in rows],
        priority_rows=rows,
        top_missing_limit=100,
    )

    assert [row["normalized_name"] for row in audit.priority_missing] == [
        "LEITE TRIANGULO 1L",
        "CAFE VASCONCELOS 500G",
    ]
    assert all(row["coverage_status"] == "missing" for row in audit.priority_missing)


def test_priority_missing_respects_limit():
    rows = [
        ProductPriorityRow(f"PRODUTO MARCA {index} 500G", f"PRODUTO MARCA {index} 500G", 10 - index, 1, False, 10 - index)
        for index in range(5)
    ]
    audit = audit_library(Library([]), priority_rows=rows, top_missing_limit=2)
    assert len(audit.priority_missing) == 2


def test_payload_exposes_phase2_coverage_contract():
    audit = audit_library(
        Library([Asset("a", product_name="MONSTER 473ML")]),
        ["MONSTER 473ML", "LEITE TRIANGULO 1L"],
    )
    data = payload(audit)

    assert data["coverage"]["catalog_products"] == 2
    assert data["coverage"]["auto_approved"] == 1
    assert data["coverage"]["without_any_image"] == 1
    assert "priority_missing" in data
