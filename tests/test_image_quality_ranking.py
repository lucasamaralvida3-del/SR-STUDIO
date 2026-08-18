from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from srstudio.images.quality import ImageQualityAnalyzer, asset_quality_score
from srstudio.images.safe_library import SafeImageLibrary


@dataclass
class Asset:
    megapixels: float
    mode: str = "RGB"
    metadata: dict = field(default_factory=dict)


def _product_like(path: Path, *, size=(900, 1200), alpha=False) -> Path:
    mode = "RGBA" if alpha else "RGB"
    background = (255, 255, 255, 0) if alpha else "white"
    image = Image.new(mode, size, background)
    draw = ImageDraw.Draw(image)
    w, h = size
    fill = (40, 120, 210, 255) if alpha else (40, 120, 210)
    draw.rounded_rectangle((w * .22, h * .08, w * .78, h * .91), radius=max(8, w // 20), fill=fill)
    detail = (240, 210, 30, 255) if alpha else (240, 210, 30)
    draw.rectangle((w * .31, h * .25, w * .69, h * .42), fill=detail)
    image.save(path)
    return path


def test_product_quality_rewards_resolution_and_clean_alpha_cutout(tmp_path):
    analyzer = ImageQualityAnalyzer()
    low = _product_like(tmp_path / "low.png", size=(160, 220), alpha=False)
    high = _product_like(tmp_path / "high.png", size=(1200, 1600), alpha=True)

    low_quality = analyzer.product_quality(low)
    high_quality = analyzer.product_quality(high)

    assert high_quality.resolution_score > low_quality.resolution_score
    assert high_quality.transparency_score > low_quality.transparency_score
    assert high_quality.score > low_quality.score


def test_known_price_and_text_probabilities_penalize_crop_quality(tmp_path):
    image = _product_like(tmp_path / "candidate.png", alpha=True)
    analyzer = ImageQualityAnalyzer()

    clean = analyzer.product_quality(image)
    contaminated = analyzer.product_quality(
        image,
        metadata={"contains_text_probability": .9, "contains_price_probability": .95},
    )

    assert contaminated.score < clean.score
    assert "text-overlay" in contaminated.penalties
    assert "price-overlay" in contaminated.penalties


def test_asset_quality_score_prefers_persisted_value_and_never_opens_pixels():
    assert asset_quality_score(Asset(10.0, metadata={"quality_score": .31})) == .31
    assert asset_quality_score(Asset(.1, mode="RGBA")) > asset_quality_score(Asset(.1, mode="RGB"))


def test_safe_library_persists_quality_once_on_import(tmp_path):
    source = _product_like(tmp_path / "MONSTER 473ML.png", alpha=True)
    library = SafeImageLibrary(tmp_path / "bank")

    asset = library.learn_product_image(source, "MONSTER 473ML", confidence=.95)
    stored = library.all()[0]

    assert asset.id == stored.id
    assert 0.0 <= float(stored.metadata["quality_score"]) <= 1.0
    assert "resolution_score" in stored.metadata
    assert "sharpness_score" in stored.metadata
