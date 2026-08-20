from __future__ import annotations

"""Structural full-card fidelity gate for Quinta3 Meat Strip.

This is intentionally stricter than the previous CARD/role IoU checks.  It
verifies that the real source-derived visual subtree exists in SR Scene, not
merely that semantic bounding boxes overlap the supervised rectangles.
"""

from dataclasses import asdict, dataclass, field
from typing import Any
import math

from .model import BindingRole, NodeKind, Rect
from .slot_corpus_full_card import (
    MEAT_STRIP_SOURCE_CLUSTER_NODE_COUNT,
    MEAT_STRIP_SOURCE_PAGE_BACKGROUND,
    MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU,
    MEAT_STRIP_SOURCE_STRIP_FILL,
    SOURCE_SHA256,
    meat_full_card_profile,
)


@dataclass(slots=True)
class FullCardFidelityReport:
    profile_id: str
    expected_source_node_count: int = MEAT_STRIP_SOURCE_CLUSTER_NODE_COUNT
    reconstructed_subtree_node_count: int = 0
    expected_reconstructed_subtree_node_count: int = 0
    visual_decorative_node_count: int = 0
    expected_visual_decorative_node_count: int = 0
    role_nodes_ok: bool = False
    visual_nodes_ok: bool = False
    asset_identity_ok: bool = False
    z_order_ok: bool = False
    fills_ok: bool = False
    strokes_ok: bool = False
    shape_types_ok: bool = False
    relative_transforms_ok: bool = False
    opacity_ok: bool = False
    clipping_masks_ok: bool = False
    complete_subtree_ok: bool = False
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        checks = (
            self.role_nodes_ok,
            self.visual_nodes_ok,
            self.asset_identity_ok,
            self.z_order_ok,
            self.fills_ok,
            self.strokes_ok,
            self.shape_types_ok,
            self.relative_transforms_ok,
            self.opacity_ok,
            self.clipping_masks_ok,
            self.complete_subtree_ok,
        )
        return all(checks) and not self.issues

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ok"] = self.ok
        return payload


def evaluate_meat_full_card(page, slot, *, profile_id: str | None = None) -> FullCardFidelityReport:
    profile_id = str(profile_id or slot.metadata.get("full_card_profile") or slot.metadata.get("supervised_profile") or "costela")
    profile = meat_full_card_profile(profile_id)
    report = FullCardFidelityReport(profile_id=profile_id)
    root = page.node(str(slot.metadata.get("root_node_id") or ""))
    if root is None:
        report.issues.append("root-missing")
        return report

    subtree_ids = [root.id, *page.descendants(root.id)]
    subtree = [page.node(node_id) for node_id in subtree_ids]
    subtree = [node for node in subtree if node is not None]
    report.reconstructed_subtree_node_count = len(subtree)

    visual_ids = [str(node_id) for node_id in slot.metadata.get("full_card_visual_nodes") or []]
    visual_nodes = [page.node(node_id) for node_id in visual_ids if page.node(node_id) is not None]
    report.visual_decorative_node_count = len(visual_nodes)
    has_separator = bool(profile.get("separator_source_id")) and str(slot.metadata.get("full_card_strip_position") or "") in {"first", "middle"}
    report.expected_visual_decorative_node_count = 5 if has_separator else 4
    # Root + semantic IMAGE/NAME/CURRENCY/INTEGER/DECIMAL/UNIT + semantic
    # PRICEBLOCK container + full-card visual/context nodes.
    report.expected_reconstructed_subtree_node_count = 8 + report.expected_visual_decorative_node_count

    synthetic = [
        node
        for node in subtree
        if node.metadata.get("item_slot_image_backplate") or node.metadata.get("item_slot_price_background")
    ]
    if synthetic:
        report.issues.append("synthetic-role-only-visuals-remain")

    role_ok = True
    for key, binding in {
        "image": BindingRole.IMAGE,
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }.items():
        node = page.node(str(slot.node_by_role.get(binding.value) or ""))
        source = profile["roles"][key]
        if node is None or str(node.metadata.get("source_shape_id") or "") != str(source["source_id"]):
            role_ok = False
            report.issues.append(f"role-source-mismatch:{key}")
    report.role_nodes_ok = role_ok

    by_source = {
        str(node.metadata.get("source_shape_id") or ""): node
        for node in visual_nodes
        if str(node.metadata.get("source_shape_id") or "")
    }
    required_visual = {"2", "3", "4"}
    if has_separator:
        required_visual.add(str(profile["separator_source_id"]))
    report.visual_nodes_ok = required_visual <= set(by_source) and any(
        node.metadata.get("source_kind") == "inherited-slide-background" for node in visual_nodes
    )
    if not report.visual_nodes_ok:
        report.issues.append("source-visual-subtree-incomplete")

    image = page.node(str(slot.node_by_role.get(BindingRole.IMAGE.value) or ""))
    source_asset = profile["image_asset"]
    report.asset_identity_ok = bool(
        image
        and str(image.metadata.get("image_sha256") or "") == str(source_asset["sha256"])
        and str(image.metadata.get("pptx_internal_media") or "") == str(source_asset["internal_media"])
        and str(image.metadata.get("full_card_source_node") or "").lower() in {"true", "1"}
    )
    if not report.asset_identity_ok:
        report.issues.append("image-asset-provenance-mismatch")

    report.z_order_ok = _z_order_ok(page, slot, profile, by_source)
    if not report.z_order_ok:
        report.issues.append("z-order-mismatch")

    background = next((node for node in visual_nodes if node.metadata.get("source_kind") == "inherited-slide-background"), None)
    strip = by_source.get("3")
    report.fills_ok = bool(
        background
        and background.style.get("fill") == MEAT_STRIP_SOURCE_PAGE_BACKGROUND
        and strip
        and strip.style.get("fill") == MEAT_STRIP_SOURCE_STRIP_FILL
    )
    if not report.fills_ok:
        report.issues.append("fill-mismatch")

    if has_separator:
        separator = by_source.get(str(profile["separator_source_id"]))
        source_root_w = float(profile["root_emu"][2])
        expected_stroke = MEAT_STRIP_SOURCE_SEPARATOR_WIDTH_EMU / source_root_w * root.transform.width
        report.strokes_ok = bool(
            separator
            and separator.style.get("stroke") == MEAT_STRIP_SOURCE_STRIP_FILL
            and math.isclose(float(separator.style.get("stroke_width") or 0.0), expected_stroke, rel_tol=1e-8, abs_tol=1e-6)
        )
    else:
        report.strokes_ok = True
    if not report.strokes_ok:
        report.issues.append("stroke-mismatch")

    report.shape_types_ok = bool(
        background
        and background.kind is NodeKind.RECT
        and strip
        and strip.kind is NodeKind.PATH
        and by_source.get("4")
        and by_source["4"].kind is NodeKind.RECT
        and (not has_separator or by_source[str(profile["separator_source_id"])].kind is NodeKind.LINE)
        and isinstance(strip.metadata.get("custom_path"), dict)
    )
    if not report.shape_types_ok:
        report.issues.append("shape-type-or-custgeom-mismatch")

    report.relative_transforms_ok = _relative_transforms_ok(page, slot, root.rect.normalized(), profile)
    if not report.relative_transforms_ok:
        report.issues.append("relative-transform-mismatch")

    report.opacity_ok = all(math.isclose(float(node.opacity), 1.0, abs_tol=1e-9) for node in subtree)
    if not report.opacity_ok:
        report.issues.append("opacity-mismatch")

    fill_rect = dict(image.style.get("fill_rect") or {}) if image is not None else {}
    expected_fill_rect = dict(source_asset["fill_rect"])
    # Meat image custGeom is an axis-aligned rectangle, so no additional
    # clip_path is expected.  Musculo still preserves its non-zero fillRect
    # outsets exactly.
    report.clipping_masks_ok = bool(
        image
        and all(math.isclose(float(fill_rect.get(key, 0.0)), float(expected_fill_rect[key]), abs_tol=1e-9) for key in ("l", "t", "r", "b"))
        and not image.metadata.get("clip_path")
        and image.metadata.get("source_geometry") == "custGeom-axis-aligned-rect"
    )
    if not report.clipping_masks_ok:
        report.issues.append("fillrect-or-clip-mismatch")

    report.complete_subtree_ok = bool(
        report.reconstructed_subtree_node_count == report.expected_reconstructed_subtree_node_count
        and report.visual_decorative_node_count == report.expected_visual_decorative_node_count
        and int(slot.metadata.get("full_card_source_cluster_node_count") or 0) == MEAT_STRIP_SOURCE_CLUSTER_NODE_COUNT
        and str(slot.metadata.get("full_card_source_sha256") or "") == SOURCE_SHA256
        and not synthetic
    )
    if not report.complete_subtree_ok:
        report.issues.append("complete-subtree-count-or-provenance-mismatch")
    return report


def _z_order_ok(page, slot, profile: dict[str, Any], by_source: dict[str, Any]) -> bool:
    for key, binding in {
        "image": BindingRole.IMAGE,
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }.items():
        node = page.node(str(slot.node_by_role.get(binding.value) or ""))
        if node is None or int(node.z_index) != int(profile["roles"][key]["z"]):
            return False
    strip = by_source.get("3")
    overlay = by_source.get("4")
    if strip is None or overlay is None or int(strip.z_index) != 0 or int(overlay.z_index) != 1:
        return False
    separator_id = profile.get("separator_source_id")
    if separator_id and str(slot.metadata.get("full_card_strip_position") or "") in {"first", "middle"}:
        separator = by_source.get(str(separator_id))
        if separator is None or int(separator.z_index) != 2:
            return False
    return True


def _relative_transforms_ok(page, slot, root: Rect, profile: dict[str, Any]) -> bool:
    for key, binding in {
        "image": BindingRole.IMAGE,
        "name": BindingRole.NAME,
        "currency": BindingRole.CURRENCY,
        "integer": BindingRole.PRICE_REAIS,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
    }.items():
        node = page.node(str(slot.node_by_role.get(binding.value) or ""))
        if node is None:
            return False
        expected = profile["roles"][key]["relative"]
        actual = _relative(node.rect.normalized(), root)
        if any(not math.isclose(float(a), float(b), rel_tol=1e-8, abs_tol=2e-7) for a, b in zip(actual, expected)):
            return False
    source_ratio = float(profile["root_emu"][3]) / float(profile["root_emu"][2])
    return math.isclose(root.height / max(root.width, 1e-9), source_ratio, rel_tol=1e-9, abs_tol=1e-9)


def _relative(child: Rect, parent: Rect) -> tuple[float, float, float, float]:
    return (
        (child.x - parent.x) / max(parent.width, 1e-9),
        (child.y - parent.y) / max(parent.height, 1e-9),
        child.width / max(parent.width, 1e-9),
        child.height / max(parent.height, 1e-9),
    )
