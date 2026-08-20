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

# Runtime extensions historically patch/mutate these private semantic symbols
# on ``semantic_blocks`` itself.  Keep shared objects here so those existing
# guards still affect the mature legacy implementation behind this facade.
_PRICE_ROLE_ALIASES = _legacy._PRICE_ROLE_ALIASES
_APP_PRICE_ROLE_ALIASES = _legacy._APP_PRICE_ROLE_ALIASES
_PRODUCT_ROLE_NAMES = _legacy._PRODUCT_ROLE_NAMES
_CURRENCY_RE = _legacy._CURRENCY_RE


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

    # ``semantic_runtime.install_complete_price_recovery_guard`` wraps this
    # symbol on the public module.  Delegate the legacy builder through that
    # already-certified guard so explicit named/wholesale bindings stay reserved
    # and native complete prices retain ``complete_price_token`` metadata.
    runtime_recovery = globals().get("_recover_unbound_price_blocks")
    if callable(runtime_recovery):
        _legacy._recover_unbound_price_blocks = runtime_recovery


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


def __getattr__(name: str):
    """Keep private runtime compatibility without duplicating legacy helpers."""

    if name.startswith("_") and hasattr(_legacy, name):
        return getattr(_legacy, name)
    raise AttributeError(name)


_recover_unbound_price_blocks = _legacy._recover_unbound_price_blocks
_make_price_block = _legacy._make_price_block
_mark_recovered_editable = _legacy._mark_recovered_editable
_bounds_dict = _legacy._bounds_dict
_geometry = _legacy._geometry
_stable_node_key = _legacy._stable_node_key
_clean_text = _legacy._clean_text
