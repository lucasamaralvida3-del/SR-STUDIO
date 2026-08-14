from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter

from apply_beta5_fixes import patch_sidebar, patch_pre_generation_dialog

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "sr_studio"


def rebuild_brand_from_url(url: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "SR-Studio-Beta5-Publisher", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
    if len(raw) < 5000:
        raise RuntimeError(f"Fonte da logo muito pequena: {len(raw)} bytes")

    image = Image.open(io.BytesIO(raw))
    image.load()
    image = image.convert("RGBA")

    probe = image.convert("RGB").resize((96, 96), Image.Resampling.LANCZOS)
    pixels = list(probe.getdata())
    total = len(pixels)
    black = sum(1 for r, g, b in pixels if r < 25 and g < 25 and b < 25) / total
    white = sum(1 for r, g, b in pixels if r > 235 and g > 235 and b > 235) / total
    blue = sum(1 for r, g, b in pixels if b > 110 and b > r * 1.15 and b > g * 1.05) / total
    if black >= 0.12 or white <= 0.08 or blue <= 0.08:
        raise RuntimeError(
            f"Logo oficial reprovada: black={black:.3f}, white={white:.3f}, blue={blue:.3f}"
        )

    hd = image.resize((2048, 2048), Image.Resampling.LANCZOS)
    hd = hd.filter(ImageFilter.UnsharpMask(radius=0.8, percent=90, threshold=3))
    assets = APP / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    logo = assets / "SR_logo.png"
    icon = assets / "SR_Studio.ico"
    hd.save(logo, "PNG", optimize=True)
    hd.save(
        icon,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (96, 96), (128, 128), (256, 256)],
    )

    with Image.open(logo) as check:
        check.load()
        if check.size != (2048, 2048):
            raise RuntimeError(f"Logo final com tamanho incorreto: {check.size}")
    if icon.stat().st_size < 10000:
        raise RuntimeError("ICO final parece incompleto")
    print("BRAND_BETA5_V2_OK", len(raw), logo.stat().st_size, icon.stat().st_size, round(black, 3), round(white, 3), round(blue, 3))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logo-url", required=True)
    args = parser.parse_args()
    patch_sidebar()
    patch_pre_generation_dialog()
    rebuild_brand_from_url(args.logo_url)
    print("BETA5_FIXES_V2_APPLIED")


if __name__ == "__main__":
    main()
