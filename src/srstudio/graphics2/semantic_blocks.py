from __future__ import annotations

"""G2 semantic blocks with IMAGE/CARD-first recovery and legacy fallback.

The mature semantic-block implementation remains the compatibility fallback in
``_semantic_blocks_legacy``.  This front door only adds source-proven semantic
vocabulary and a conservative IMAGE-first pre-pass; it does not replace the
existing PriceBlock/ProductCard model.
"""

from . import _semantic_blocks_legacy as _legacy
from .model import NodeKind
from .semantic_card_first import recover_product_cards_image_first
from .semantic_vocabulary import UNIT_RE, is_name_forbidden_token, semantic_label_role

SemanticBlock = _legacy.SemanticBlock
SemanticBlockReport = _legacy.SemanticBlockReport
semantic_block = _legacy.semantic_block
semantic_owner = _legacy.semantic_owner
semantic_member_ids = _legacy.semantic_member_ids
_UNIT_RE = UNIT_RE


def _configure_legacy_vocabulary() -> None:
    _legacy._UNIT_RE = UNIT_RE
    _legacy._PRODUCT_ROLE_NAMES.update({"promotion", "club_label"})
    original = getattr(_legacy, "_quinta3_original_name_candidate", None)
    if original is None:
        original = _legacy._is_product_name_candidate
        _legacy._quinta3_original_name_candidate = original

    def guarded_name_candidate(node):
        text = " ".join(str(getattr(node, "text", "") or "").replace("\n", " ").split()).strip()
        return not is_name_forbidden_token(text) and bool(original(node))

    _legacy._is_product_name_candidate = guarded_name_candidate

    original_clear = getattr(_legacy, "_quinta3_original_clear_recovered_slots", None)
    if original_clear is None:
        original_clear = _legacy._clear_recovered_slots
        _legacy._quinta3_original_clear_recovered_slots = original_clear

    def clear_recovered_slots_preserving_image_first(page):
        keep = {
            slot_id: slot
            for slot_id, slot in page.slots.items()
            if bool(slot.metadata.get("semantic_image_first"))
        }
        original_clear(page)
        page.slots.update(keep)

    _legacy._clear_recovered_slots = clear_recovered_slots_preserving_image_first

    original_recover = getattr(_legacy, "_quinta3_original_recover_unbound_price_blocks", None)
    if original_recover is None:
        original_recover = _legacy._recover_unbound_price_blocks
        _legacy._quinta3_original_recover_unbound_price_blocks = original_recover

    def recover_with_complete_units(page):
        blocks = list(original_recover(page))
        return _attach_unambiguous_complete_units(page, blocks)

    _legacy._recover_unbound_price_blocks = recover_with_complete_units


def _attach_unambiguous_complete_units(page, blocks):
    """Attach a literal unit to a recovered complete amount when unambiguous.

    Canva sometimes exports ``R$`` + ``92,77`` as a complete amount while
    keeping ``CADA``/``QUILO`` in its own text node.  The legacy complete-price
    branch intentionally did not consume a unit.  Keep that branch intact and
    enrich only when exactly one official, still-unbound unit overlaps the local
    price region.
    """

    output = []
    for block in blocks:
        if block.roles.get("unit") or not block.roles.get("complete"):
            output.append(block)
            continue
        bounds = dict(block.bounds or {})
        x = float(bounds.get("x") or 0.0)
        y = float(bounds.get("y") or 0.0)
        width = max(float(bounds.get("width") or 0.0), 1.0)
        height = max(float(bounds.get("height") or 0.0), 1.0)
        left = x - width * 0.08
        right = x + width * 1.08
        top = y - height * 0.25
        bottom = y + height * 1.25
        candidates = []
        for node in page.nodes.values():
            if node.kind is not NodeKind.TEXT or not node.visible:
                continue
            if node.metadata.get("semantic_price_block_id"):
                continue
            text = " ".join(str(node.text or "").replace("\n", " ").split()).strip()
            if not UNIT_RE.fullmatch(text):
                continue
            rect = node.rect.normalized()
            if rect.right < left or rect.x > right or rect.bottom < top or rect.y > bottom:
                continue
            candidates.append(node)
        if len(candidates) != 1:
            output.append(block)
            continue
        roles = {key: list(value) for key, value in block.roles.items()}
        roles["unit"] = [candidates[0].id]
        replacement = _legacy._make_price_block(
            page,
            block.id,
            block.slot_id,
            roles,
            source=str(block.metadata.get("source") or "spatial-recovery-complete"),
            recovered=bool(block.metadata.get("recovered")),
        )
        replacement.metadata.update(dict(block.metadata or {}))
        output.append(replacement)
    return output


def _has_supervised_card_first_signal(document) -> bool:
    """Enable the pre-pass only when the source exposes Quinta3-era semantics."""

    for page in document.pages:
        for node in page.nodes.values():
            text = " ".join(str(getattr(node, "text", "") or "").replace("\n", " ").split()).strip()
            if not text:
                continue
            if text.upper().lstrip("/") in {"CADA", "QUILO"}:
                return True
            if semantic_label_role(text) in {"promotion", "club_label"}:
                return True
    return False


def _inside_generated_pptx_group(page, node) -> bool:
    parent_id = str(node.parent_id or "")
    seen: set[str] = set()
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = page.node(parent_id)
        if parent is None:
            break
        if parent.kind is NodeKind.GROUP and bool(parent.metadata.get("pptx_group_generated")):
            return True
        parent_id = str(parent.parent_id or "")
    return False


def _recover_card_first_without_preempting_grouped_legacy(document) -> int:
    """Run IMAGE-first only where legacy has no explicit PPTX group anchor."""

    hidden = []
    for page in document.pages:
        for node in page.nodes.values():
            if node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND} or not node.visible:
                continue
            if _inside_generated_pptx_group(page, node):
                hidden.append(node)
                node.visible = False
    try:
        return recover_product_cards_image_first(document)
    finally:
        for node in hidden:
            node.visible = True


def build_semantic_blocks(document):
    """Run CARD/IMAGE-first recovery, then the unchanged legacy fallback."""

    _configure_legacy_vocabulary()
    image_first = 0
    if _has_supervised_card_first_signal(document):
        image_first = _recover_card_first_without_preempting_grouped_legacy(document)
    report = _legacy.build_semantic_blocks(document)
    document.metadata["semantic_recovery_order"] = ["card-image-first", "price-first-fallback"]
    document.metadata["semantic_image_first_candidates"] = int(image_first)
    return report


def _is_product_name_candidate(node) -> bool:
    _configure_legacy_vocabulary()
    return bool(_legacy._is_product_name_candidate(node))


def is_official_unit_text(value: str) -> bool:
    return bool(UNIT_RE.fullmatch(" ".join(str(value or "").split()).strip()))

_recover_unbound_price_blocks = _legacy._recover_unbound_price_blocks
_make_price_block = _legacy._make_price_block
_mark_recovered_editable = _legacy._mark_recovered_editable
_bounds_dict = _legacy._bounds_dict
_geometry = _legacy._geometry
_clean_text = _legacy._clean_text
