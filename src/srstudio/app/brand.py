from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageTk


BRAND_DIR = Path("srstudio") / "assets" / "brand"
LOGO_NAME = "SR_logo.png"
ICON_NAME = "SR_Studio.ico"


def brand_dir() -> Path:
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen) / BRAND_DIR
    return Path(__file__).resolve().parents[1] / "assets" / "brand"


def logo_path() -> Path:
    return brand_dir() / LOGO_NAME


def icon_path() -> Path:
    return brand_dir() / ICON_NAME


def brand_assets_available() -> bool:
    return logo_path().is_file() and icon_path().is_file()


def load_logo_photo(master, size: int = 56) -> ImageTk.PhotoImage | None:
    """Carrega a logo oficial com transparência, mantendo um fallback seguro."""
    path = logo_path()
    if not path.is_file():
        return None
    try:
        with Image.open(path) as source:
            image = source.convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        x = (size - image.width) // 2
        y = (size - image.height) // 2
        canvas.alpha_composite(image, (x, y))
        return ImageTk.PhotoImage(canvas, master=master)
    except (OSError, ValueError, RuntimeError):
        return None
