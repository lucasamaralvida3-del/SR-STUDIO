from __future__ import annotations

"""Role-level reconstruction metrics for the five supervised Quinta 3 families.

Metrics are geometric and normalized to the ProductCard/root.  They deliberately
remain separate by role; no global score can hide a bad UNIT/NAME behind a good
IMAGE.  The Meat Strip expectation now uses the full visual ProductCard root;
the other four families stay on their previous supervised role contracts until
they enter the full-card migration in later rounds.
"""

from collections import defaultdict
from statistics import mean
from typing import Any

from .model import BindingRole, GraphicsDocument, Rect
from .operations import GraphicsSession
from .slot_corpus_calibration import QUINTA3_SUPERVISED_PROFILES
from .slot_corpus_full_card import MEAT_FAMILY_ID, meat_full_card_profile
from .slot_corpus_variant_runtime import create_quinta3_item_slot

BASELINE_FAMILY_METRICS: dict[str, dict[str, float]] = {
    "quinta3-meat-strip": {"image": 0.8172, "name": 0.7931, "priceblock": 0.8666, "unit": 0.4708},
    "quinta3-wood-plaque": {"image": 0.8118, "name": 0.9017, "priceblock": 0.7981, "unit": 0.4430, "secondary_price": 0.9993, "promotion": 0.9977, "club": 0.9992},
    "quinta3-compact-promo": {"image": 0.89555, "name": 0.6065, "priceblock": 0.67955, "unit": 0.2703, "secondary_price": 0.5525, "promotion": 0.38075},
    "quinta3-club-side": {"image": 0.8927, "name": 0.6833, "priceblock": 0.7238, "unit": 0.3932, "secondary_price": 0.5033, "promotion": 0.4537, "club": 0.0},
    "quinta3-stationery-round": {"image": 0.8971, "name": 0.3587, "priceblock": 0.6877, "unit": 0.3645},
}


def measure_supervised_family_metrics() -> dict[str, dict[str, float]]:
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for profile_id, profile in QUINTA3_SUPERVISED_PROFILES.items():
        session = GraphicsSession(GraphicsDocument(name=f"metric:{profile_id}"))
        slot = create_quinta3_item_slot(
            session,
            profile["family_id"],
            variant=profile["variant"],
            parameters={"supervisedProfile": profile_id},
            x=100,
            y=120,
        )
        page = session.page
        root = page.node(slot.metadata["root_node_id"])
        if root is None:
            continue
        family = profile["family_id"]
        buckets[family]["card"].append(1.0)
        buckets[family]["product_center_error"].append(0.0)
        areas = slot.metadata["role_area_nodes"]
        expected = _expected_role_bounds(profile_id, profile)

        image_nodes = [page.node(slot.node_by_role[BindingRole.IMAGE.value])]
        extras = slot.metadata.get("extra_bindings") or {}
        for node_id in extras.get(BindingRole.IMAGE.value, []):
            image_nodes.append(page.node(node_id))
        image_rects = [node.rect.normalized() for node in image_nodes if node is not None]
        actual_image = _union(image_rects)
        buckets[family]["image"].append(_iou(_relative(actual_image, root.rect.normalized()), expected["image"]))

        for role, key in (("name", "name"), ("price", "priceblock"), ("unit", "unit")):
            node = page.node(areas[role])
            if node is not None:
                buckets[family][key].append(_iou(_relative(node.rect.normalized(), root.rect.normalized()), expected[role]))

        if "secondaryPrice" in expected:
            group = next((page.node(node_id) for node_id in slot.metadata.get("quinta3_variant_nodes", []) if page.node(node_id) is not None and page.node(node_id).name == "SECONDARY PRICE AREA"), None)
            if group is not None:
                buckets[family]["secondary_price"].append(_iou(_relative(group.rect.normalized(), root.rect.normalized()), expected["secondaryPrice"]))
        if "promotion" in expected and extras.get("promotion"):
            node = page.node(extras["promotion"][0])
            buckets[family]["promotion"].append(_iou(_relative(node.rect.normalized(), root.rect.normalized()), expected["promotion"]))
        if "club" in expected and extras.get("club_label"):
            node = page.node(extras["club_label"][0])
            buckets[family]["club"].append(_iou(_relative(node.rect.normalized(), root.rect.normalized()), expected["club"]))

    return {
        family: {role: round(mean(values), 6) for role, values in sorted(roles.items()) if values}
        for family, roles in sorted(buckets.items())
    }


def _expected_role_bounds(profile_id: str, profile: dict[str, Any]) -> dict[str, list[float]]:
    if profile["family_id"] != MEAT_FAMILY_ID:
        return dict(profile["roleBounds"])
    full = meat_full_card_profile(profile_id)
    roles = full["roles"]
    return {
        "image": list(roles["image"]["relative"]),
        "name": list(roles["name"]["relative"]),
        "price": _union_relative([
            roles["currency"]["relative"],
            roles["integer"]["relative"],
            roles["decimal"]["relative"],
        ]),
        "unit": list(roles["unit"]["relative"]),
    }


def _union_relative(rects: list[list[float]]) -> list[float]:
    left = min(float(rect[0]) for rect in rects)
    top = min(float(rect[1]) for rect in rects)
    right = max(float(rect[0]) + float(rect[2]) for rect in rects)
    bottom = max(float(rect[1]) + float(rect[3]) for rect in rects)
    return [left, top, right - left, bottom - top]


def _relative(rect: Rect, root: Rect) -> list[float]:
    return [
        (rect.x - root.x) / max(root.width, 1e-9),
        (rect.y - root.y) / max(root.height, 1e-9),
        rect.width / max(root.width, 1e-9),
        rect.height / max(root.height, 1e-9),
    ]


def _union(rects: list[Rect]) -> Rect:
    if not rects:
        return Rect()
    out = rects[0]
    for rect in rects[1:]:
        out = out.union(rect)
    return out


def _iou(a: list[float], b: list[float]) -> float:
    ax, ay, aw, ah = (float(v) for v in a)
    bx, by, bw, bh = (float(v) for v in b)
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = max(0.0, aw) * max(0.0, ah) + max(0.0, bw) * max(0.0, bh) - intersection
    return 1.0 if union <= 1e-12 else intersection / union
