from __future__ import annotations

"""withoutBG product cutout engine, lazy/offline on CPU and not on the UI thread.

SDK: Apache-2.0. Local model includes separately licensed DINOv3 weights;
see withoutBG's NOTICE and THIRD_PARTY_LICENSES before redistributing weights.
The SR Studio build never bundles model weights and downloads on first request.
"""

from hashlib import sha256
from pathlib import Path
from threading import Lock
import os

from .image_replace import normalize_local_image_source

_MODEL = None
_MODEL_LOCK = Lock()


def _get_model():
    global _MODEL
    if _MODEL is None:
        # Imported only when an actual product needs processing. The first
        # call may download ~1.5 GB of ONNX weights; subsequent calls reuse it.
        from withoutbg import WithoutBG
        _MODEL = WithoutBG.open_weights()
    return _MODEL


def remove_product_background(source: str | Path, *, cache_root: str | Path | None = None) -> Path:
    """Generate an RGBA PNG cache entry, preserving the unmodified source.

    Thread-safe model reuse, single-source hash cache, and atomic output prevent
    partially written images when two imports happen close together.
    """
    path = normalize_local_image_source(str(source))
    root = Path(cache_root) if cache_root is not None else (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SRStudio" / "Cache" / "BackgroundRemoval"
    )
    root.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    output = root / (digest.hexdigest() + ".png")
    if output.is_file() and output.stat().st_size > 0:
        return output
    # Product PNGs already cut out should remain untouched, with zero model
    # initialization and no unnecessary ~1.5 GB first-run download.
    from PIL import Image
    with Image.open(path) as original:
        if "A" in original.getbands():
            lo, hi = original.getchannel("A").getextrema()
            if lo < 255:
                return path

    with _MODEL_LOCK:
        if output.is_file() and output.stat().st_size > 0:
            return output
        image = _get_model().remove_background(str(path))
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        temp = root / (output.stem + ".partial.png")
        try:
            image.save(temp, format="PNG")
            if not temp.is_file() or temp.stat().st_size == 0:
                raise RuntimeError("withoutBG não gerou uma imagem PNG válida.")
            temp.replace(output)
        finally:
            temp.unlink(missing_ok=True)
    return output
