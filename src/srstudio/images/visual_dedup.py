from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps


@dataclass(frozen=True, slots=True)
class VisualDuplicateSignals:
    hamming_distance: int
    aspect_delta: float
    same_orientation: bool
    content_distance: float | None = None


def hamming_hex(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except (TypeError, ValueError):
        return 64


def compact_rgb_signature(image: Image.Image, *, grid: int = 4) -> str:
    """Return a tiny color/content signature for dHash collision rejection.

    The signature is not an identity hash. It preserves coarse RGB layout so two
    low-detail images with the same dHash still need similar color/content before
    they can be treated as near-duplicates.
    """
    grid = max(2, min(8, int(grid)))
    prepared = ImageOps.exif_transpose(image).convert("RGBA")
    background = Image.new("RGBA", prepared.size, (255, 255, 255, 255))
    prepared = Image.alpha_composite(background, prepared).convert("RGB").resize((grid, grid))
    return bytes(prepared.tobytes()).hex()


def rgb_signature_distance(left: str, right: str) -> float:
    try:
        left_bytes = bytes.fromhex(left)
        right_bytes = bytes.fromhex(right)
    except (TypeError, ValueError):
        return 1.0
    if not left_bytes or len(left_bytes) != len(right_bytes):
        return 1.0
    return sum(abs(a - b) for a, b in zip(left_bytes, right_bytes)) / (255.0 * len(left_bytes))


def _aspect(width: int, height: int) -> float:
    return max(1, int(width)) / max(1, int(height))


def visual_duplicate_signals(
    left_hash: str,
    right_hash: str,
    left_size: tuple[int, int],
    right_size: tuple[int, int],
    *,
    left_rgb_signature: str = "",
    right_rgb_signature: str = "",
) -> VisualDuplicateSignals:
    left_width, left_height = left_size
    right_width, right_height = right_size
    left_aspect = _aspect(left_width, left_height)
    right_aspect = _aspect(right_width, right_height)
    aspect_delta = abs(left_aspect - right_aspect) / max(left_aspect, right_aspect, 1e-9)
    left_orientation = (left_width > left_height) - (left_width < left_height)
    right_orientation = (right_width > right_height) - (right_width < right_height)
    content_distance = None
    if left_rgb_signature and right_rgb_signature:
        content_distance = rgb_signature_distance(left_rgb_signature, right_rgb_signature)
    return VisualDuplicateSignals(
        hamming_distance=hamming_hex(left_hash, right_hash),
        aspect_delta=aspect_delta,
        same_orientation=left_orientation == right_orientation,
        content_distance=content_distance,
    )


def is_conservative_visual_duplicate(
    left_hash: str,
    right_hash: str,
    left_size: tuple[int, int],
    right_size: tuple[int, int],
    *,
    left_rgb_signature: str = "",
    right_rgb_signature: str = "",
    max_hamming_distance: int = 6,
    max_aspect_delta: float = 0.08,
    max_content_distance: float = 0.12,
) -> bool:
    """Precision-first perceptual duplicate candidate gate.

    Exact identity remains SHA-256's responsibility. dHash finds resized or
    recompressed candidates, geometry rejects incompatible crops/layouts, and a
    compact RGB signature rejects same-shape low-detail collisions. Legacy records
    without a color signature retain the geometry-gated behavior until touched by
    the safe library; no destructive migration is required.
    """
    signals = visual_duplicate_signals(
        left_hash,
        right_hash,
        left_size,
        right_size,
        left_rgb_signature=left_rgb_signature,
        right_rgb_signature=right_rgb_signature,
    )
    if signals.hamming_distance > max_hamming_distance:
        return False
    if not signals.same_orientation or signals.aspect_delta > max_aspect_delta:
        return False
    if signals.content_distance is not None and signals.content_distance > max_content_distance:
        return False
    return True
