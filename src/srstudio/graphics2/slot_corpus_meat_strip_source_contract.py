from __future__ import annotations

"""Exact immutable source-page contract for the supervised Quinta3 Meat Strip.

The source identity remains owned by ``slot_corpus_full_card``.  This module
re-exports that identity together with the exact ``p:presentation/p:sldSz`` so
all page-space consumers use one canonical mapping contract instead of copying
page dimensions into ownership/runtime code.
"""

from .slot_corpus_full_card import SOURCE_FILE, SOURCE_SHA256

# Exact p:presentation/p:sldSz of SOURCE_FILE / SOURCE_SHA256.
SOURCE_PAGE_WIDTH_EMU = 10287000.0
SOURCE_PAGE_HEIGHT_EMU = 12852400.0

__all__ = (
    "SOURCE_FILE",
    "SOURCE_SHA256",
    "SOURCE_PAGE_WIDTH_EMU",
    "SOURCE_PAGE_HEIGHT_EMU",
)
