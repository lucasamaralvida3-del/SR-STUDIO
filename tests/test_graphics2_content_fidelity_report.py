from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from srstudio.graphics2.content_fidelity import compare_content_masks
from srstudio.graphics2.content_fidelity_report import summarize_content_groups


def _mask(box=None):
    image = Image.new("L", (80, 60), 0)
    if box is not None:
        ImageDraw.Draw(image).rectangle(box, fill=255)
    return image


def test_named_summary_exposes_text_and_wordart_without_touching_official_gate():
    perfect_text = compare_content_masks(_mask((10, 10, 29, 29)), _mask((10, 10, 29, 29)))
    shifted_wordart = compare_content_masks(_mask((20, 15, 39, 34)), _mask((25, 15, 44, 34)))

    summary = summarize_content_groups({"text": [perfect_text], "WordArt": [shifted_wordart]})
    payload = summary.to_dict()

    assert payload["TEXT_REGION_SCORE"] == pytest.approx(100.0)
    assert 0.0 < payload["WORDART_REGION_SCORE"] < 100.0
    assert 0.0 < payload["CONTENT_REGION_SCORE"] < 100.0
    assert payload["FOREGROUND_PIXEL_PASS"] > 0.0
    assert payload["FOREGROUND_CHANGED_AREA"] > 0.0
    assert payload["regions"] == 2
    assert payload["diagnostic_only"] is True
    assert payload["official_gate_unchanged"] is True


def test_unknown_categories_still_contribute_to_overall_diagnostic():
    missing = compare_content_masks(_mask((10, 10, 19, 19)), _mask())
    summary = summarize_content_groups({"OTHER": [missing]})

    assert summary.regions == 1
    assert summary.content_region_score == 0.0
    assert summary.text_region_score == 0.0
    assert summary.wordart_region_score == 0.0
