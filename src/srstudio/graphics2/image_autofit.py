"""Non-destructive alpha-bound fitting for product PNGs.

Calculates normalized source crop insets; it never rewrites a user's image.
A mostly opaque or damaged/non-alpha image keeps its original framing.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse


def source_path(source: str) -> Path:
    text = str(source or "").strip()
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        location = unquote(parsed.path)
        if len(location) > 2 and location[0] == "/" and location[2] == ":":
            location = location[1:]
        text = location
    return Path(text).expanduser()


def visible_product_crop(source: str, *, padding: float = 0.025) -> dict[str, float]:
    """Return inset crop for PNG transparency, or {} if uncertain.

    Padding retains a visible margin around tall bottles, thin packages,
    antialiased product edges and soft shadows. Semi-transparent pixels are
    included to protect those shadows. Opaque pictures are not cropped.
    """
    try:
        from PIL import Image
        path = source_path(source)
        if not path.is_file():
            return {}
        with Image.open(path) as image:
            if "A" not in image.getbands():
                return {}
            width, height = image.size
            if width < 4 or height < 4:
                return {}
            # Alpha noise under 3/255 is not treated as a product pixel.
            alpha = image.getchannel("A").point(lambda p: 255 if p >= 3 else 0)
            bounds = alpha.getbbox()
            if not bounds:
                return {}
            x0, y0, x1, y1 = bounds
            margin_x = max(2, round(width * padding))
            margin_y = max(2, round(height * padding))
            x0, y0 = max(0, x0 - margin_x), max(0, y0 - margin_y)
            x1, y1 = min(width, x1 + margin_x), min(height, y1 + margin_y)
            if (x1 - x0) * (y1 - y0) < width * height * 0.005:
                return {}
            result = {
                "l": x0 / width, "t": y0 / height,
                "r": (width - x1) / width, "b": (height - y1) / height,
            }
            # A tiny alpha border isn't worth a crop / resampling.
            return result if max(result.values()) >= 0.035 else {}
    except (OSError, ValueError, ImportError):
        return {}


def fitted_product_source(document, node) -> str:
    source = str(node.metadata.get("bound_image_source") or "").strip()
    if source:
        return source
    asset = document.assets.get(str(node.asset_id or ""))
    return str(asset.source or "") if asset is not None else ""
