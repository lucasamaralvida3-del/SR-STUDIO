from dataclasses import dataclass

from srstudio.images.benchmark import benchmark_lookup


@dataclass
class Asset:
    id: str
    product_key: str
    product_name: str
    aliases: tuple = ()
    kind: str = "product"
    review_status: str = "accepted"
    preferred: bool = False
    confidence: float = .95
    usage_count: int = 0
    megapixels: float = 1.0


class Library:
    index_path = None

    def __init__(self, assets):
        self.assets = assets

    def all(self, *, status="", kind=""):
        rows = self.assets
        if status:
            rows = [row for row in rows if row.review_status == status]
        return rows


def test_lookup_benchmark_reports_metadata_only_latency_and_matches():
    assets = [
        Asset("1", "MONSTER 473ML", "MONSTER 473ML"),
        Asset("2", "CAFE VASCONCELOS 500G", "CAFE VASCONCELOS 500G"),
    ]

    result = benchmark_lookup(
        Library(assets),
        ["MONSTER 473ML", "CAFE VASCONCELOS 500G"],
        repeats=3,
    )

    assert result.assets == 2
    assert result.queries == 6
    assert result.matches == 6
    assert result.refresh_ms >= 0.0
    assert result.median_ms >= 0.0
    assert result.p95_ms >= 0.0
    assert result.max_ms >= result.p95_ms
