from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PARTS = [
    ROOT / "staging" / "beta61_logo" / "exact_part1.b64",
    ROOT / "staging" / "beta61_logo" / "exact_part2.b64",
    ROOT / "staging" / "beta61_logo" / "exact_part3.b64",
    ROOT / "staging" / "beta61_logo" / "exact_part4.b64",
]
ASSETS = ROOT / "src" / "sr_studio" / "assets"
LOGO_PNG = ASSETS / "SR_logo.png"
ICON_ICO = ASSETS / "SR_Studio.ico"

EXPECTED_BASE64_LENGTH = 19136
EXPECTED_SOURCE_SIZE = 14352
EXPECTED_SOURCE_SHA256 = "82e9f1568d1f4e70e2a1521876133b8c61643c89f587cfa9009e99744cee69f4"
EXPECTED_DIMENSION = (512, 512)
ICON_SIZES = [(16,16),(24,24),(32,32),(48,48),(64,64),(96,96),(128,128),(256,256)]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pixel_stats(image: Image.Image) -> tuple[float, float, float]:
    rgb = image.convert("RGB")
    pixels = list(rgb.getdata())
    total = max(1, len(pixels))
    near_black = sum(1 for r, g, b in pixels if max(r, g, b) < 20) / total
    near_white = sum(1 for r, g, b in pixels if min(r, g, b) > 245) / total
    brand_blue = sum(1 for r, g, b in pixels if b > 120 and b > r * 1.20 and b > g * 1.05) / total
    return near_black, near_white, brand_blue


def validate_visual(image: Image.Image, label: str) -> None:
    if image.size != EXPECTED_DIMENSION:
        raise RuntimeError(f"{label}: dimensão inválida {image.size}, esperado {EXPECTED_DIMENSION}")
    near_black, near_white, brand_blue = pixel_stats(image)
    # A logo oficial enviada pelo usuário não possui região preta. Um retângulo preto,
    # como ocorreu nas Betas anteriores, faz esta validação falhar antes da publicação.
    if near_black >= 0.001:
        raise RuntimeError(f"{label}: pixels quase pretos demais ({near_black:.4%})")
    if near_white < 0.30:
        raise RuntimeError(f"{label}: área branca inesperada ({near_white:.2%})")
    if brand_blue < 0.35:
        raise RuntimeError(f"{label}: área azul inesperada ({brand_blue:.2%})")
    print(f"{label}: black={near_black:.6%} white={near_white:.2%} blue={brand_blue:.2%}")


def main() -> None:
    chunks = []
    for part in SOURCE_PARTS:
        text = "".join(part.read_text(encoding="ascii").split())
        if len(text) != 4784:
            raise RuntimeError(f"Bloco da logo com tamanho inválido: {part.name}={len(text)}")
        chunks.append(text)
    text = "".join(chunks)
    if len(text) != EXPECTED_BASE64_LENGTH:
        raise RuntimeError(f"Base64 da logo com comprimento inválido: {len(text)}")

    raw = base64.b64decode(text, validate=True)
    if len(raw) != EXPECTED_SOURCE_SIZE:
        raise RuntimeError(f"Fonte da logo com tamanho inválido: {len(raw)}")
    source_sha = sha256_bytes(raw)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"Fonte da logo com SHA inválido: {source_sha}")

    with Image.open(io.BytesIO(raw)) as source:
        source.load()
        logo = source.convert("RGB")
    validate_visual(logo, "FONTE_LOGO")

    ASSETS.mkdir(parents=True, exist_ok=True)
    logo.save(LOGO_PNG, format="PNG", optimize=True, compress_level=9)
    # Reabrir o PNG gravado é proposital: garante que o arquivo distribuído é íntegro,
    # não apenas que a imagem em memória estava correta.
    with Image.open(LOGO_PNG) as check:
        check.load()
        saved_logo = check.convert("RGB")
    validate_visual(saved_logo, "PNG_DISTRIBUIDO")

    saved_logo.save(ICON_ICO, format="ICO", sizes=ICON_SIZES)
    with Image.open(ICON_ICO) as icon:
        icon.load()
        available = set(getattr(icon, "ico", icon).sizes()) if hasattr(icon, "ico") else {icon.size}
    required = set(ICON_SIZES)
    if not required.issubset(available):
        raise RuntimeError(f"ICO incompleto: {sorted(available)}")

    print("BETA61_LOGO_OK")
    print("PNG", LOGO_PNG.stat().st_size, sha256_bytes(LOGO_PNG.read_bytes()))
    print("ICO", ICON_ICO.stat().st_size, sha256_bytes(ICON_ICO.read_bytes()))
    print("ICO_SIZES", sorted(available))


if __name__ == "__main__":
    main()
