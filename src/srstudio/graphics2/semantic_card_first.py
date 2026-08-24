from __future__ import annotations

"""Conservative IMAGE/CARD-first Smart Slot recovery for static G2 PPTX pages.

This pass runs before the legacy PriceBlock-first recovery.  It never changes
source geometry.  It only binds a card when a real image, a product-name
candidate and a complete split price (currency/integer/decimal/unit) agree in a
small local region.  Anything ambiguous is left untouched for the legacy
fallback.
"""

from dataclasses import dataclass
from math import hypot
import re
from typing import Iterable

from .model import BindingRole, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Rect, SmartSlot
from .semantic_vocabulary import CURRENCY_RE, UNIT_RE, is_name_forbidden_token, semantic_label_role

_INTEGER_RE = re.compile(r"^\d{1,3}$")
_CENTS_RE = re.compile(r"^[,.]\d{1,2}$")
_ALPHA_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")


@dataclass(frozen=True, slots=True)
class _PriceCandidate:
    currency: GraphicsNode
    integer: GraphicsNode
    decimal: GraphicsNode
    unit: GraphicsNode

    @property
    def nodes(self) -> tuple[GraphicsNode, ...]:
        return (self.currency, self.integer, self.decimal, self.unit)

    @property
    def bounds(self) -> Rect:
        rect = self.currency.rect.normalized()
        for node in self.nodes[1:]:
            rect = rect.union(node.rect.normalized())
        return rect


def recover_product_cards_image_first(document: GraphicsDocument) -> int:
    """Bind unambiguous real-image product cards before legacy price-first work."""

    recovered = 0
    for page in document.pages:
        recovered += _recover_page(page)
    if recovered:
        document.metadata["semantic_image_first_recovered"] = int(recovered)
    return recovered


def _recover_page(page: GraphicsPage) -> int:
    bound_ids = {
        str(node_id)
        for slot in page.slots.values()
        for node_id in [*slot.node_by_role.values(), *[item for values in _extra_values(slot) for item in values]]
        if node_id
    }
    prices = _price_candidates(page, bound_ids)
    if not prices:
        return 0
    images = [
        node for node in page.nodes.values()
        if node.id not in bound_ids
        and node.visible
        and node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}
        and node.rect.width > 0 and node.rect.height > 0
        and (node.rect.width * node.rect.height) < page.width * page.height * 0.45
    ]
    if not images:
        return 0

    used_prices: set[str] = set()
    used_names: set[str] = set()
    used_images: set[str] = set()
    recovered = 0
    # Larger product images anchor first; decorative micro-assets are naturally
    # disfavoured and never win merely because they are close to a price.
    images.sort(key=lambda node: -(node.rect.width * node.rect.height))
    for image in images:
        if image.id in used_images:
            continue
        price = _best_price_for_image(page, image, prices, used_prices)
        if price is None:
            continue
        name = _best_name(page, image, price, used_names, bound_ids)
        if name is None:
            continue
        card_rect = image.rect.normalized().union(price.bounds).union(name.rect.normalized())
        copies = _image_copies(page, image, card_rect, images, used_images)
        labels = _labels_in_card(page, card_rect, bound_ids)
        secondary = _secondary_price(page, price, prices, card_rect, used_prices)
        slot = _make_slot(page, copies, name, price, secondary, labels, card_rect)
        if slot is None:
            continue
        used_names.add(name.id)
        used_images.update(node.id for node in copies)
        used_prices.add(price.integer.id)
        if secondary is not None:
            used_prices.add(secondary.integer.id)
        recovered += 1
    return recovered


def _extra_values(slot) -> Iterable[list[str]]:
    extras = slot.metadata.get("extra_bindings")
    if not isinstance(extras, dict):
        return []
    return [list(value) for value in extras.values() if isinstance(value, (list, tuple))]


def _clean(node: GraphicsNode) -> str:
    return " ".join(str(node.text or "").replace("\n", " ").split()).strip()


def _price_candidates(page: GraphicsPage, excluded: set[str]) -> list[_PriceCandidate]:
    text = [node for node in page.nodes.values() if node.kind is NodeKind.TEXT and node.visible and node.id not in excluded]
    currencies = [n for n in text if CURRENCY_RE.fullmatch(_clean(n))]
    integers = [n for n in text if _INTEGER_RE.fullmatch(_clean(n))]
    decimals = [n for n in text if _CENTS_RE.fullmatch(_clean(n))]
    units = [n for n in text if UNIT_RE.fullmatch(_clean(n))]
    out: list[_PriceCandidate] = []
    claimed: set[str] = set()
    integers.sort(key=lambda n: -(n.rect.width * n.rect.height))
    for integer in integers:
        currency = _near_token(integer, currencies, claimed, "currency")
        decimal = _near_token(integer, decimals, claimed, "decimal")
        unit = _near_token(integer, units, claimed, "unit")
        if not currency or not decimal or not unit:
            continue
        ids = {currency.id, integer.id, decimal.id, unit.id}
        if len(ids) != 4:
            continue
        candidate = _PriceCandidate(currency, integer, decimal, unit)
        if candidate.bounds.width > page.width * 0.34 or candidate.bounds.height > page.height * 0.18:
            continue
        out.append(candidate)
        claimed.update(ids)
    return out


def _near_token(integer: GraphicsNode, candidates: list[GraphicsNode], claimed: set[str], role: str) -> GraphicsNode | None:
    ir = integer.rect.normalized()
    ix, iy = ir.center_x, ir.center_y
    scale = max(ir.height, 1.0)
    best: tuple[float, GraphicsNode] | None = None
    for node in candidates:
        if node.id in claimed:
            continue
        nr = node.rect.normalized()
        dx = (nr.center_x - ix) / scale
        dy = (nr.center_y - iy) / scale
        if role == "currency" and not (-1.75 <= dx <= 0.20 and abs(dy) <= 0.90):
            continue
        if role == "decimal" and not (-0.10 <= dx <= 1.45 and -1.10 <= dy <= 0.65):
            continue
        if role == "unit" and not (-0.10 <= dx <= 1.55 and -0.55 <= dy <= 1.25):
            continue
        score = hypot(dx, dy)
        if best is None or score < best[0]:
            best = (score, node)
    return best[1] if best else None


def _best_price_for_image(page: GraphicsPage, image: GraphicsNode, prices: list[_PriceCandidate], used: set[str]) -> _PriceCandidate | None:
    ir = image.rect.normalized()
    best: tuple[float, _PriceCandidate] | None = None
    for price in prices:
        if price.integer.id in used:
            continue
        pr = price.bounds
        dx = abs(pr.center_x - ir.center_x) / max(page.width, 1.0)
        # A source corpus allows price below, overlaid on, or at the side of the
        # product image; local distance is still a strong card signal.
        dy = abs(pr.center_y - ir.center_y) / max(page.height, 1.0)
        if dx > 0.24 or dy > 0.25:
            continue
        score = dx * 1.4 + dy - min(ir.width * ir.height / max(page.width * page.height, 1.0), 0.15) * 0.5
        if best is None or score < best[0]:
            best = (score, price)
    return best[1] if best else None


def _is_name_candidate(node: GraphicsNode) -> bool:
    if node.kind is not NodeKind.TEXT or not node.visible:
        return False
    text = _clean(node)
    if len(text) < 3 or len(text) > 140 or not _ALPHA_RE.search(text) or _DATE_RE.search(text):
        return False
    if is_name_forbidden_token(text):
        return False
    return True


def _best_name(page: GraphicsPage, image: GraphicsNode, price: _PriceCandidate, used: set[str], bound: set[str]) -> GraphicsNode | None:
    card_seed = image.rect.normalized().union(price.bounds)
    margin_x = page.width * 0.08
    margin_y = page.height * 0.08
    region = Rect(max(0.0, card_seed.x - margin_x), max(0.0, card_seed.y - margin_y), min(page.width, card_seed.right + margin_x) - max(0.0, card_seed.x - margin_x), min(page.height, card_seed.bottom + margin_y) - max(0.0, card_seed.y - margin_y))
    candidates: list[tuple[float, GraphicsNode]] = []
    for node in page.nodes.values():
        if node.id in used or node.id in bound or not _is_name_candidate(node):
            continue
        nr = node.rect.normalized()
        if not _intersects(nr, region):
            continue
        dx = abs(nr.center_x - card_seed.center_x) / max(region.width, 1.0)
        dy = abs(nr.center_y - price.bounds.center_y) / max(region.height, 1.0)
        font = float(node.style.get("font_size") or 0.0)
        # Prefer a local text box distinct from price labels; source names may be
        # above or below the image depending on the learned family.
        score = dx * 1.4 + dy * 0.45 - min(font / 100.0, 0.35)
        candidates.append((score, node))
    candidates.sort(key=lambda item: (item[0], item[1].id))
    return candidates[0][1] if candidates else None


def _secondary_price(page: GraphicsPage, primary: _PriceCandidate, prices: list[_PriceCandidate], card: Rect, used: set[str]) -> _PriceCandidate | None:
    candidates: list[tuple[float, _PriceCandidate]] = []
    for other in prices:
        if other.integer.id == primary.integer.id or other.integer.id in used:
            continue
        ob = other.bounds
        expanded = Rect(max(0.0, card.x - card.width * 0.20), max(0.0, card.y - card.height * 0.20), card.width * 1.40, card.height * 1.40)
        if not _intersects(ob, expanded):
            continue
        dx = abs(ob.center_x - primary.bounds.center_x) / max(page.width, 1.0)
        dy = abs(ob.center_y - primary.bounds.center_y) / max(page.height, 1.0)
        if dx > 0.20 or dy > 0.14:
            continue
        size_penalty = max(0.0, (ob.width * ob.height) - (primary.bounds.width * primary.bounds.height)) / max(page.width * page.height, 1.0)
        candidates.append((dx + dy + size_penalty, other))
    candidates.sort(key=lambda item: (item[0], item[1].integer.id))
    return candidates[0][1] if candidates else None


def _labels_in_card(page: GraphicsPage, card: Rect, bound: set[str]) -> dict[str, GraphicsNode]:
    expanded = Rect(max(0.0, card.x - card.width * 0.15), max(0.0, card.y - card.height * 0.15), card.width * 1.30, card.height * 1.30)
    found: dict[str, tuple[float, GraphicsNode]] = {}
    for node in page.nodes.values():
        if node.id in bound or node.kind is not NodeKind.TEXT or not node.visible:
            continue
        role = semantic_label_role(_clean(node))
        if not role or not _intersects(node.rect.normalized(), expanded):
            continue
        distance = hypot(node.rect.center_x - card.center_x, node.rect.center_y - card.center_y)
        if role not in found or distance < found[role][0]:
            found[role] = (distance, node)
    return {role: item[1] for role, item in found.items()}


def _image_copies(page: GraphicsPage, anchor: GraphicsNode, card: Rect, images: list[GraphicsNode], used: set[str]) -> list[GraphicsNode]:
    copies = [anchor]
    anchor_asset = str(anchor.asset_id or anchor.metadata.get("image_sha256") or anchor.metadata.get("media_sha256") or "")
    if not anchor_asset:
        return copies
    expanded = Rect(max(0.0, card.x - card.width * 0.15), max(0.0, card.y - card.height * 0.15), card.width * 1.30, card.height * 1.30)
    for node in images:
        if node.id == anchor.id or node.id in used:
            continue
        candidate_asset = str(node.asset_id or node.metadata.get("image_sha256") or node.metadata.get("media_sha256") or "")
        if candidate_asset == anchor_asset and _intersects(node.rect.normalized(), expanded):
            copies.append(node)
    return copies


def _make_slot(page: GraphicsPage, images: list[GraphicsNode], name: GraphicsNode, primary: _PriceCandidate, secondary: _PriceCandidate | None, labels: dict[str, GraphicsNode], card: Rect) -> SmartSlot | None:
    stable = str(images[0].metadata.get("source_name") or images[0].name or images[0].id).strip()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", stable).strip("-").lower() or images[0].id
    slot_id = f"slot:image-first:{safe}"
    if slot_id in page.slots:
        return page.slots[slot_id]
    node_by_role = {
        BindingRole.IMAGE.value: images[0].id,
        BindingRole.NAME.value: name.id,
        BindingRole.CURRENCY.value: primary.currency.id,
        BindingRole.PRICE_REAIS.value: primary.integer.id,
        BindingRole.PRICE_CENTS.value: primary.decimal.id,
        BindingRole.UNIT.value: primary.unit.id,
    }
    extras: dict[str, list[str]] = {}
    if len(images) > 1:
        extras[BindingRole.IMAGE.value] = [node.id for node in images[1:]]
    if secondary is not None:
        extras.update({
            "app_price_currency": [secondary.currency.id],
            "app_price_integer": [secondary.integer.id],
            "app_price_cents": [secondary.decimal.id],
            "app_unit": [secondary.unit.id],
        })
    for role, node in labels.items():
        extras[role] = [node.id]
    center = {"x": card.center_x, "y": card.center_y}
    slot = SmartSlot(
        id=slot_id,
        name=_clean(name),
        page_id=page.id,
        node_by_role=node_by_role,
        confidence=0.97,
        metadata={
            "source": "canva-smart-slot",
            "semantic_recovered": True,
            "semantic_image_first": True,
            "recovered_spatial": True,
            "extra_bindings": extras,
            "image_node_ids": [node.id for node in images],
            "product_center": center,
            "product_card_bounds": {"x": card.x, "y": card.y, "width": card.width, "height": card.height},
            "product_snapshot": {},
        },
    )
    page.slots[slot.id] = slot
    return slot


def _intersects(a: Rect, b: Rect) -> bool:
    return not (a.right < b.x or a.x > b.right or a.bottom < b.y or a.y > b.bottom)
