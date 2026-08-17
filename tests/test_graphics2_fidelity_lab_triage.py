from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from srstudio.graphics2.fidelity_lab import _scene_aware_triage
from srstudio.graphics2.model import BindingRole, GraphicsNode, GraphicsPage, NodeKind, Transform


def test_scene_aware_triage_writes_artifacts_and_attributes_price(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (100, 100), "white").save(baseline)
    changed = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(changed)
    draw.rectangle((20, 20, 49, 49), fill="black")
    changed.save(candidate)

    page = GraphicsPage(id="page_1", name="Quinta Filé", width=100, height=100)
    page.add_node(
        GraphicsNode(
            id="price_reais",
            kind=NodeKind.TEXT,
            name="Preço reais",
            transform=Transform(x=20, y=20, width=30, height=30),
            binding_role=BindingRole.PRICE_REAIS,
            z_index=20,
        )
    )

    payload = _scene_aware_triage(
        baseline,
        candidate,
        page,
        output=tmp_path,
        stem="quinta-file",
        pixel_tolerance=0,
    )

    assert payload["available"] is True
    assert Path(payload["triage_report"]).is_file()
    assert Path(payload["heatmap"]).is_file()
    assert Path(payload["attribution_report"]).is_file()
    region = payload["attribution"]["regions"][0]
    suspect = region["suspects"][0]
    assert suspect["node_id"] == "price_reais"
    assert suspect["binding_role"] == "price_reais"
    assert suspect["diagnostic_hint"].startswith("preço:")


def test_scene_aware_triage_does_not_fail_pipeline_for_size_mismatch(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.png"
    candidate = tmp_path / "candidate.png"
    Image.new("RGB", (100, 100), "white").save(baseline)
    Image.new("RGB", (120, 100), "white").save(candidate)
    page = GraphicsPage(id="page_1", width=100, height=100)

    payload = _scene_aware_triage(
        baseline,
        candidate,
        page,
        output=tmp_path,
        stem="mismatch",
        pixel_tolerance=12,
    )

    assert payload["available"] is False
    assert "mesmo tamanho" in payload["reason"]
    assert payload["triage_report"] == ""
    assert payload["attribution_report"] == ""
