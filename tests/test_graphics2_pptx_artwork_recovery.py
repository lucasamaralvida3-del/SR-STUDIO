from __future__ import annotations

from srstudio.graphics2.pptx_artwork import PptxArtworkRecoveryReport


def test_artwork_report_empty_is_ready():
    report = PptxArtworkRecoveryReport()
    assert report.coverage == 1.0
    assert report.large_artwork_coverage == 1.0
