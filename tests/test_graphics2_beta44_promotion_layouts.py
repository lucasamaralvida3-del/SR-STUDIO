from srstudio.graphics2.promotion_layouts import plan_promotion
import pytest


@pytest.mark.parametrize("mode,n", [
    ("individual", 1), ("six", 6), ("seven", 7), ("eleven", 11),
    ("auto", 1), ("auto", 5), ("auto", 6), ("auto", 7), ("auto", 11),
])
def test_compositions_obey_logo_reservation(mode, n):
    for variation in range(3):
        plan = plan_promotion(mode, count=n if mode == "auto" else None,
                              variation=variation)
        assert len(plan.placements) == n
        assert {p.index for p in plan.placements} == set(range(n))
        assert all(p.y >= plan.logo_reserved for p in plan.placements)


def test_auto_layout_variants_differ():
    a = plan_promotion("auto", count=11, variation=0)
    b = plan_promotion("auto", count=11, variation=1)
    assert a.placements != b.placements


@pytest.mark.parametrize("count", [0, -1, 25])
def test_invalid_counts_rejected(count):
    with pytest.raises(ValueError):
        plan_promotion("auto", count=count)


def test_user_can_increase_reserved_header():
    plan = plan_promotion("seven", logo_reserved=.4)
    assert all(slot.y >= .4 for slot in plan.placements)
