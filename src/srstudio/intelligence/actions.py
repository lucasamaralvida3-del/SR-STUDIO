from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class StudioAction:
    action: str
    target_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    confidence: float = 1.0
    requires_review: bool = False


class ActionRegistry:
    """Whitelisted bridge between SR IA suggestions and deterministic Studio operations."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[StudioAction], Any]] = {}

    def register(self, action_name: str, handler: Callable[[StudioAction], Any]) -> None:
        self._handlers[action_name] = handler

    def allowed_actions(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def execute(self, action: StudioAction, *, approved: bool = False) -> Any:
        if action.action not in self._handlers:
            raise ValueError(f"Ação SR IA não permitida: {action.action}")
        if action.requires_review and not approved:
            raise PermissionError("Esta ação requer revisão/aprovação antes da execução.")
        return self._handlers[action.action](action)


SAFE_DEFAULT_ACTIONS = {
    "move_card",
    "resize_card",
    "highlight_card",
    "set_layout",
    "reflow_page",
    "balance_pages",
    "group_cards",
    "set_text_style",
    "replace_product_image",
}

COMMERCIAL_REVIEW_ACTIONS = {
    "change_price",
    "change_unit",
    "change_cpf_limit",
    "change_validity",
}


def classify_action(action_name: str) -> dict[str, bool]:
    return {
        "known": action_name in SAFE_DEFAULT_ACTIONS or action_name in COMMERCIAL_REVIEW_ACTIONS,
        "commercial": action_name in COMMERCIAL_REVIEW_ACTIONS,
        "requires_review": action_name in COMMERCIAL_REVIEW_ACTIONS,
    }
