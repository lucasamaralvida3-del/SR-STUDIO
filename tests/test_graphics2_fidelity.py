from __future__ import annotations

import json

from PIL import Image, ImageDraw

from srstudio.graphics2.fidelity import (
    FidelityPolicy,
    compare_images,
    load_manifest,
    run_suite,
    write_report,
)


def _sample(path, *, shift: int = 0, size: tuple[int, int] = (320, 240)):
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30 + shift, 25, 290 + shift, 210), fill="#0C4A8A")
    draw.rectangle((70 + shift, 70, 250 + shift, 170), fill="#FDE047")
    draw.text((100 + shift, 105), "SR 33,64", fill="black")
    image.save(path)


def test_identical_images_pass_strict_gate_and_write_diff(tmp_path):
    baseline = tmp_path / "baseline.png"
    candidate = tmp_path / "candidate.png"
    diff = tmp_path / "artifacts" / "diff.png"
    _sample(baseline)
    _sample(candidate)
    result = compare_images(
        baseline,
        candidate,
        policy=FidelityPolicy(min_score=0.9999, min_pixel_pass_ratio=1.0, max_changed_ratio=0.0),
        diff_path=diff,
    )
    assert result.passed
    assert result.metrics.score == 1.0
    assert result.metrics.pixel_pass_ratio == 1.0
    assert result.metrics.changed_ratio == 0.0
    assert result.metrics.changed_bbox is None
    assert diff.is_file()


def test_shifted_layout_is_rejected_by_visual_gate(tmp_path):
    baseline = tmp_path / "baseline.png"
    candidate = tmp_path / "candidate.png"
    _sample(baseline)
    _sample(candidate, shift=18)
    result = compare_images(
        baseline,
        candidate,
        policy=FidelityPolicy(min_score=0.995, min_pixel_pass_ratio=0.99, max_changed_ratio=0.01),
    )
    assert not result.passed
    assert result.metrics.score < 0.995 or result.metrics.changed_ratio > 0.01
    assert result.metrics.changed_bbox is not None
    assert result.reasons


def test_dimension_mismatch_fails_even_when_resize_is_visually_similar(tmp_path):
    baseline = tmp_path / "baseline.png"
    candidate = tmp_path / "candidate.png"
    _sample(baseline, size=(320, 240))
    _sample(candidate, size=(640, 480))
    result = compare_images(
        baseline,
        candidate,
        policy=FidelityPolicy(require_same_size=True, min_score=0.0, min_pixel_pass_ratio=0.0, max_changed_ratio=1.0),
    )
    assert not result.passed
    assert result.metrics.baseline_width == 320
    assert result.metrics.candidate_width == 640
    assert any("dimensão divergente" in reason for reason in result.reasons)


def test_manifest_suite_runs_multiple_cases_and_writes_json_report(tmp_path):
    baseline = tmp_path / "reference.png"
    good = tmp_path / "good.png"
    bad = tmp_path / "bad.png"
    _sample(baseline)
    _sample(good)
    _sample(bad, shift=25)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "defaults": {
                    "min_score": 0.995,
                    "min_pixel_pass_ratio": 0.99,
                    "pixel_tolerance": 6,
                    "max_changed_ratio": 0.01,
                },
                "cases": [
                    {"name": "controle", "baseline": "reference.png", "candidate": "good.png"},
                    {"name": "regressao", "baseline": "reference.png", "candidate": "bad.png"},
                ],
            }
        ),
        encoding="utf-8",
    )
    cases = load_manifest(manifest)
    suite = run_suite(cases, artifacts_dir=tmp_path / "out")
    report = write_report(suite, tmp_path / "out" / "suite-report.json")
    assert len(suite.cases) == 2
    assert suite.cases[0].passed
    assert not suite.cases[1].passed
    assert not suite.passed
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert len(payload["cases"]) == 2
