from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VisualDuplicateSignals:
    hamming_distance: int
    aspect_delta: float
    same_orientation: bool


def hamming_hex(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except (TypeError, ValueError):
        return 64


def _aspect(width: int, height: int) -> float:
    return max(1, int(width)) / max(1, int(height))


def visual_duplicate_signals(
    left_hash: str,
    right_hash: str,
    left_size: tuple[int, int],
    right_size: tuple[int, int],
) -> VisualDuplicateSignals:
    left_width, left_height = left_size
    right_width, right_height = right_size
    left_aspect = _aspect(left_width, left_height)
    right_aspect = _aspect(right_width, right_height)
    aspect_delta = abs(left_aspect - right_aspect) / max(left_aspect, right_aspect, 1e-9)
    left_orientation = (left_width > left_height) - (left_width < left_height)
    right_orientation = (right_width > right_height) - (right_width < right_height)
    return VisualDuplicateSignals(
        hamming_distance=hamming_hex(left_hash, right_hash),
        aspect_delta=aspect_delta,
        same_orientation=left_orientation == right_orientation,
    )


def is_conservative_visual_duplicate(
    left_hash: str,
    right_hash: str,
    left_size: tuple[int, int],
    right_size: tuple[int, int],
    *,
    max_hamming_distance: int = 6,
    max_aspect_delta: float = 0.08,
) -> bool:
    """Precision-first perceptual duplicate candidate gate.

    dHash is useful for resized/recompressed copies but it is not an identity
    primitive. Low-detail assets can collide completely. A perceptual candidate is
    therefore accepted only when dHash, orientation and aspect ratio all agree.
    Exact identity remains SHA-256's responsibility.
    """
    signals = visual_duplicate_signals(left_hash, right_hash, left_size, right_size)
    return (
        signals.hamming_distance <= max_hamming_distance
        and signals.same_orientation
        and signals.aspect_delta <= max_aspect_delta
    )
