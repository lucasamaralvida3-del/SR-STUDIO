from __future__ import annotations

from decimal import Decimal

from srstudio.importers.pipeline import UnifiedImportPipeline
from srstudio.importers.pptx.reader import PptxElement, PptxSlide
from srstudio.importers.pptx.semantic import PriceCluster, SemanticCard
from srstudio.importers.pptx.slot_validation import SmartSlotValidator


def _safe_candidate(*, image: PptxElement | None = None) -> SemanticCard:
    name = PptxElement("text", x=110, y=180, width=170, height=45, text="ARROZ TIO JOAO 5KG")
    integer = PptxElement("text", x=135, y=360, width=70, height=70, text="24")
    cents = PptxElement("text", x=205, y=370, width=45, height=35, text=",90")
    cluster = PriceCluster(value=Decimal("24.90"), integer=integer, cents=cents, elements=[integer, cents])
    return SemanticCard(
        image=image,
        name=name,
        price=integer,
        price_value=Decimal("24.90"),
        price_cluster=cluster,
        confidence=0.91,
        bounds=(80, 120, 300, 450),
    )


def test_validator_accepts_local_product_slot_and_recomputes_bounds():
    slide = PptxSlide(index=1, width=1000, height=1000)
    image = PptxElement("image", x=115, y=235, width=120, height=110, media_path="product.png")
    candidate = _safe_candidate(image=image)

    accepted, stats = SmartSlotValidator.select([candidate], slide)

    assert stats.detected == 1
    assert stats.accepted == 1
    assert stats.rejected == 0
    assert accepted[0].bounds is not None
    left, top, right, bottom = accepted[0].bounds
    assert right - left < 420
    assert bottom - top < 480


def test_validator_rejects_cross_page_name_that_would_create_giant_slot():
    slide = PptxSlide(index=1, width=1000, height=1000)
    candidate = _safe_candidate()
    candidate.name = PptxElement("text", x=780, y=100, width=180, height=40, text="PONTA DE PICANHA")
    candidate.bounds = (100, 100, 960, 450)

    accepted, stats = SmartSlotValidator.select([candidate], slide)

    assert accepted == []
    assert stats.rejected == 1


def test_validator_drops_decorative_giant_image_but_keeps_name_price_slot():
    slide = PptxSlide(index=1, width=1000, height=1000)
    decorative = PptxElement("image", x=0, y=0, width=900, height=550, media_path="background.png")
    candidate = _safe_candidate(image=decorative)

    accepted, _stats = SmartSlotValidator.select([candidate], slide)

    assert len(accepted) == 1
    assert accepted[0].image is None
    assert accepted[0].bounds is not None
    assert accepted[0].bounds[2] - accepted[0].bounds[0] < 420


def test_validator_removes_far_secondary_price_instead_of_binding_neighbor_product():
    slide = PptxSlide(index=1, width=1000, height=1000)
    candidate = _safe_candidate()
    secondary_integer = PptxElement("text", x=700, y=370, width=60, height=60, text="7")
    secondary_cents = PptxElement("text", x=760, y=375, width=40, height=30, text=",49")
    candidate.secondary_price = PriceCluster(
        value=Decimal("7.49"),
        integer=secondary_integer,
        cents=secondary_cents,
        elements=[secondary_integer, secondary_cents],
    )

    accepted, _stats = SmartSlotValidator.select([candidate], slide)

    assert len(accepted) == 1
    assert accepted[0].secondary_price is None


def test_canva_transparent_helper_shape_does_not_become_white_box():
    helper = PptxElement(
        "shape",
        x=10,
        y=10,
        width=200,
        height=100,
        metadata={"fill": "none", "outline": "#FF0000"},
    )
    converted = UnifiedImportPipeline._pptx_element(helper, 1000, 1000, 1080.0, 1080.0)

    assert converted is not None
    assert converted["fill"] == ""
    assert converted["outline"] == "#FF0000"


def test_canva_invisible_helper_shape_is_ignored():
    helper = PptxElement(
        "shape",
        x=10,
        y=10,
        width=200,
        height=100,
        metadata={"fill": "none", "outline": "none"},
    )

    assert UnifiedImportPipeline._pptx_element(helper, 1000, 1000, 1080.0, 1080.0) is None
