from __future__ import annotations

"""G2 semantic blocks with IMAGE/CARD-first recovery and legacy fallback.

The mature semantic-block implementation remains the compatibility fallback in
``_semantic_blocks_legacy``.  This front door only adds source-proven semantic
vocabulary and a conservative IMAGE-first pre-pass; it does not replace the
existing PriceBlock/ProductCard model.
"""

from . import _semantic_blocks_legacy as _legacy
from .semantic_card_first import recover_product_cards_image_first
from .semantic_vocabulary import UNIT_RE, is_name_forbidden_token

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


def build_semantic_blocks(document):
    """Run CARD/IMAGE-first recovery, then the unchanged legacy fallback."""

    _configure_legacy_vocabulary()
    image_first = recover_product_cards_image_first(document)
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
_clean_text = _legacy._clean_text
