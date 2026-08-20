from __future__ import annotations

"""Placeholder recovery compatibility front door with shared G2 vocabulary."""

from . import _semantic_placeholders_legacy as _legacy
from .semantic_vocabulary import is_name_forbidden_token

PlaceholderRecoveryReport = _legacy.PlaceholderRecoveryReport


def _configure_name_vocabulary() -> None:
    original = getattr(_legacy, "_quinta3_original_is_name_text", None)
    if original is None:
        original = _legacy._is_name_text
        _legacy._quinta3_original_is_name_text = original

    def guarded(text: str) -> bool:
        return not is_name_forbidden_token(text) and bool(original(text))

    _legacy._is_name_text = guarded


def recover_canva_image_placeholders(document):
    _configure_name_vocabulary()
    return _legacy.recover_canva_image_placeholders(document)


def _is_name_text(text: str) -> bool:
    _configure_name_vocabulary()
    return bool(_legacy._is_name_text(text))
