from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw
import pytest

from srstudio.graphics2.fidelity_triage import analyze_fidelity_regions, write_triage_report


def _image(path: Path, size=(256, 256), color="white") -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def test_triage_ranks_largest_visual_problem_first(tmp_path):
    reference = _image(tmp_path / "reference.png")
    candidate = _image(tmp_path / "candidate.png")
    with Image.open(candidate) as raw:
        image = raw.copy()
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 20, 103, 91), fill="black")
    draw.rectangle((180, 184, 205, 209), fill="#808080")
    image.save(candidate)

    heatmap = tmp_path / "heatmap.png"
    report = analyze_fidelity_regions(
        reference,
        candidate,
        pixel_tolerance=12,
        tile_size=32,
        min_tile_changed_ratio=0.01,
        heatmap_path=heatmap,
    )

    assert report.changed_pixels > 0
    assert report.changed_ratio > 0
    assert len(report.regions) >= 2
    assert report.regions[0].importance > report.regions[1].importance
    assert report.regions[0].x <= 16 <= report.regions[0].x + report.regions[0].width
    assert report.regions[0].y <= 20 <= report.regions[0].y + report.regions[0].height
    assert heatmap.is_file() and heatmap.stat().st_size > 0


def test_triage_identical_images_is_clean(tmp_path):
    reference = _image(tmp_path / "reference.png", (120, 160), "#123456")
    candidate = _image(tmp_path / "candidate.png", (120, 160), "#123456")

    report = analyze_fidelity_regions(reference, candidate)

    assert report.clean
    assert report.changed_pixels == 0
    assert report.changed_ratio == 0
    assert report.bbox is None
    assert report.regions == ()


def test_triage_rejects_different_dimensions(tmp_path):
    reference = _image(tmp_path / "reference.png", (100, 100))
    candidate = _image(tmp_path / "candidate.png", (101, 100))

    with pytest.raises(ValueError, match="mesmo tamanho"):
        analyze_fidelity_regions(reference, candidate)


def test_triage_report_is_serializable(tmp_path):
    reference = _image(tmp_path / "reference.png", (64, 64))
    candidate = _image(tmp_path / "candidate.png", (64, 64))
    with Image.open(candidate) as raw:
        image = raw.copy()
    image.putpixel((30, 30), (0, 0, 0))
    image.save(candidate)

    report = analyze_fidelity_regions(reference, candidate, tile_size=16, min_tile_changed_ratio=0)
    target = write_triage_report(report, tmp_path / "reports" / "triage.json")

    text = target.read_text(encoding="utf-8")
    assert '"changed_pixels"' in text
    assert '"regions"' in text
