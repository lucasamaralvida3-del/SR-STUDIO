from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from srstudio.images.product_priority import ProductPriorityRow
from srstudio.images.review_contact_sheet import build_review_dataset, dataset_payload, render_contact_sheet


@dataclass
class Asset:
    id: str
    product_name: str
    path: str
    product_key: str = ""
    kind: str = "product"
    review_status: str = "pending"
    preferred: bool = False
    confidence: float = .85
    megapixels: float = 1.0
    mode: str = "RGB"
    source: str = "canva"
    metadata: dict = field(default_factory=dict)


class Library:
    def __init__(self, assets):
        self.assets = list(assets)

    def all(self):
        return list(self.assets)


def _image(path: Path, size=(500, 700)) -> str:
    Image.new("RGB", size, "white").save(path)
    return str(path)


def test_review_dataset_prioritizes_frequent_product_and_limits_variants(tmp_path):
    paths = [_image(tmp_path / f"{index}.png") for index in range(5)]
    library = Library([
        Asset(f"rice-{index}", "ARROZ PATOSUL 5KG", paths[index], confidence=.80 + index * .01)
        for index in range(4)
    ] + [
        Asset("coffee", "CAFE VASCONCELOS 500G", paths[4], confidence=.88)
    ])
    priority = [
        ProductPriorityRow("ARROZ PATOSUL 5KG", "ARROZ PATOSUL 5KG", 20, 5, True, 30.75),
        ProductPriorityRow("CAFE VASCONCELOS 500G", "CAFE VASCONCELOS 500G", 3, 1, True, 6.75),
    ]

    groups = build_review_dataset(library, priority_rows=priority, candidates_per_product=3)

    assert groups[0].normalized_name == "ARROZ PATOSUL 5KG"
    assert len(groups[0].candidates) == 3
    assert groups[0].priority_score > groups[1].priority_score


def test_accepted_single_variant_with_no_pending_is_not_review_noise(tmp_path):
    path = _image(tmp_path / "accepted.png")
    library = Library([Asset("a", "MONSTER 473ML", path, review_status="accepted")])
    assert build_review_dataset(library) == ()


def test_multiple_accepted_variants_without_preferred_remain_reviewable(tmp_path):
    first = _image(tmp_path / "a.png")
    second = _image(tmp_path / "b.png")
    groups = build_review_dataset(
        Library([
            Asset("a", "DETERGENTE YPE 500ML", first, review_status="accepted"),
            Asset("b", "DETERGENTE YPE 500ML", second, review_status="accepted"),
        ])
    )
    assert len(groups) == 1
    assert len(groups[0].candidates) == 2


def test_render_contact_sheet_handles_missing_candidate_path(tmp_path):
    existing = _image(tmp_path / "existing.png")
    groups = build_review_dataset(
        Library([
            Asset("a", "TODDY 370G", existing, metadata={"quality_score": .8}),
            Asset("b", "TODDY 370G", str(tmp_path / "missing.png"), metadata={"quality_score": .7}),
        ])
    )

    output = render_contact_sheet(groups, tmp_path / "review.png", thumb_size=(100, 100), candidates_per_row=2)

    assert output.exists()
    with Image.open(output) as image:
        assert image.width > 200
        assert image.height > 100


def test_dataset_payload_is_compact_json_ready(tmp_path):
    path = _image(tmp_path / "candidate.png")
    groups = build_review_dataset(Library([Asset("a", "LEITE TRIANGULO 1L", path)]))
    payload = dataset_payload(groups)
    assert payload["products"] == 1
    assert payload["candidates"] == 1
    assert payload["groups"][0]["product_name"] == "LEITE TRIANGULO 1L"
