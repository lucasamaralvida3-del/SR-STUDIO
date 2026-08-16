from __future__ import annotations

from types import SimpleNamespace

from PIL import Image
from pypdf import PdfWriter

from srstudio.graphics2.golden_master import _aggregate_fidelity, build_parser
from srstudio.graphics2.pdf_baseline import render_pdf_baselines


def test_pdf_baseline_renders_all_pages_at_requested_width(tmp_path):
    pdf = tmp_path / "reference.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=144)
    writer.add_blank_page(width=144, height=72)
    with pdf.open("wb") as handle:
        writer.write(handle)

    pages = render_pdf_baselines(pdf, tmp_path / "baseline", target_width=360, prefix="quinta-file")

    assert len(pages) == 2
    assert pages[0].width == 360
    assert pages[0].height == 720
    assert pages[1].width == 360
    assert pages[1].height == 180
    for page in pages:
        assert page.output.is_file()
        with Image.open(page.output) as image:
            assert image.mode == "RGB"
            assert image.width == 360


def test_golden_master_aggregate_uses_worst_page_for_release_gate():
    def result(score, pixel_pass, changed, passed=True):
        metrics = SimpleNamespace(score=score, pixel_pass_ratio=pixel_pass, changed_ratio=changed)
        return SimpleNamespace(
            metrics=metrics,
            passed=passed,
            to_dict=lambda: {"passed": passed, "metrics": {"score": score}},
        )

    aggregate = _aggregate_fidelity(
        [result(0.998, 0.99, 0.01), result(0.986, 0.97, 0.03)],
        True,
        2,
        2,
    )
    assert aggregate["passed"] is True
    assert aggregate["metrics"]["score"] == 0.986
    assert aggregate["metrics"]["pixel_pass_ratio"] == 0.97
    assert aggregate["metrics"]["changed_ratio"] == 0.03
    assert aggregate["average_score"] == (0.998 + 0.986) / 2


def test_golden_master_page_count_mismatch_is_always_a_failure():
    metrics = SimpleNamespace(score=1.0, pixel_pass_ratio=1.0, changed_ratio=0.0)
    result = SimpleNamespace(
        metrics=metrics,
        passed=True,
        to_dict=lambda: {"passed": True, "metrics": {"score": 1.0}},
    )
    aggregate = _aggregate_fidelity([result], False, 1, 2)
    assert aggregate["passed"] is False
    assert aggregate["page_count_matches"] is False


def test_golden_master_cli_accepts_pptx_and_pdf_pair():
    args = build_parser().parse_args(
        [
            "OFERTAS QUINTA FILÉ NOVO.pptx",
            "OFERTAS QUINTA FILÉ NOVO.pdf",
            "--target-width",
            "2160",
            "--save-scene",
        ]
    )
    assert args.pptx.suffix.lower() == ".pptx"
    assert args.reference_pdf.suffix.lower() == ".pdf"
    assert args.target_width == 2160
    assert args.save_scene is True
