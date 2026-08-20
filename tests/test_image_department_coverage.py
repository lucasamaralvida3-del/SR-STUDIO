from dataclasses import dataclass, field

from srstudio.images.department_coverage import department_coverage, payload


@dataclass
class Asset:
    product_name: str
    product_key: str = ""
    aliases: tuple = ()
    kind: str = "product"
    review_status: str = "accepted"
    metadata: dict = field(default_factory=dict)


class Library:
    def __init__(self, assets):
        self.assets = list(assets)

    def all(self):
        return list(self.assets)


def test_department_coverage_separates_states_and_missing():
    library = Library([
        Asset("ARROZ PATOSUL 5KG", review_status="accepted"),
        Asset("DETERGENTE YPE 500ML", review_status="pending", metadata={"association_status": "probable"}),
        Asset("CERVEJA BRAHMA 350ML", review_status="pending", metadata={"association_status": "review"}),
    ])
    catalog = [
        "ARROZ PATOSUL 5KG",
        "CAFE VASCONCELOS 500G",
        "DETERGENTE YPE 500ML",
        "CERVEJA BRAHMA 350ML",
        "BANANA NANICA KG",
    ]

    rows = {row.department: row for row in department_coverage(library, catalog)}

    assert rows["mercearia"].total == 2
    assert rows["mercearia"].auto_approved == 1
    assert rows["mercearia"].without_any_image == 1
    assert rows["limpeza"].likely == 1
    assert rows["bebidas"].review_required == 1
    assert rows["hortifruti"].without_any_image == 1


def test_alias_can_cover_equivalent_catalog_spelling():
    library = Library([
        Asset("PAO DE QUEIJO SR TRADICIONAL 1KG", aliases=("PAO DE QUEIJO SR 1KG",))
    ])
    rows = {row.department: row for row in department_coverage(library, ["PAO DE QUEIJO SR 1KG"])}
    assert rows["padaria"].auto_approved == 1


def test_rejected_and_decorative_assets_never_cover_catalog():
    library = Library([
        Asset("BANANA NANICA KG", review_status="rejected"),
        Asset("DETERGENTE YPE 500ML", kind="decorative", review_status="accepted"),
    ])
    rows = {row.department: row for row in department_coverage(
        library, ["BANANA NANICA KG", "DETERGENTE YPE 500ML"]
    )}
    assert rows["hortifruti"].without_any_image == 1
    assert rows["limpeza"].without_any_image == 1


def test_payload_counts_unique_catalog_products():
    data = payload(department_coverage(Library([]), ["ARROZ PATOSUL 5KG", "ARROZ PATOSUL 5KG"]))
    assert data["catalog_products"] == 1
