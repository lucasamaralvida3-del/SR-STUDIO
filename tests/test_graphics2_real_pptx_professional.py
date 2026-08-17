from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.professional_probe import run_professional_probe
from srstudio.graphics2.qt_host import load_launch_context


_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODELS = _REPO_ROOT / "src" / "srstudio" / "assets" / "poster_templates" / "legacy" / "models"
_REAL_CARTAZ_VENDA = _MODELS / "CARTAZ_VENDA.pptx"
_REAL_SEMANTIC_TEMPLATE = _MODELS / "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx"


def test_real_cartaz_venda_runs_editor_import_persistence_and_exports(tmp_path: Path):
    """Exercise a real SR PPTX through the same import path used by the G2 editor."""

    assert _REAL_CARTAZ_VENDA.is_file(), "O corpus real CARTAZ_VENDA.pptx deve permanecer disponível para o gate G2."

    context = load_launch_context(_REAL_CARTAZ_VENDA)
    document = context.document

    assert context.source == _REAL_CARTAZ_VENDA.resolve()
    assert context.import_audit is not None
    assert document.metadata.get("graphics2_import_bridge") == 2
    assert document.metadata.get("pptx_structure")
    assert document.metadata.get("import_fingerprint_sha256")
    assert document.metadata.get("import_editability", {}).get("policy") == "content-v1"
    assert len(document.pages) >= 1

    nodes = [node for page in document.pages for node in page.nodes.values()]
    visible_text = [node for node in nodes if node.visible and node.kind.value == "text"]
    assert len(nodes) >= 4
    assert any(node.visible for node in nodes)
    assert visible_text
    assert any(not node.locked for node in visible_text), "PPTX real precisa chegar ao editor com texto editável."

    output = tmp_path / "real-pptx-probe"
    report = run_professional_probe(
        _REAL_CARTAZ_VENDA,
        output_dir=output,
        require_semantic_products=False,
    )

    assert report.ready is True, report.to_dict()
    assert report.gate_blockers == []
    assert report.persistence_ok is True
    assert report.png_ok is True
    assert report.pdf_ok is True
    assert report.page_count_before == report.page_count_after >= 1
    assert report.node_count_before == report.node_count_after >= 4
    assert Path(report.scene_path).is_file()
    assert Path(report.png_path).is_file()
    assert Path(report.pdf_path).is_file()
    assert report.errors == []


def test_real_two_price_template_recovers_professional_product_semantics(tmp_path: Path):
    """Require real ProductCard/PriceBlock/SmartSlot semantics from a production SR template."""

    assert _REAL_SEMANTIC_TEMPLATE.is_file()
    context = load_launch_context(_REAL_SEMANTIC_TEMPLATE)
    text_diagnostics = [
        {
            "id": node.id,
            "name": node.name,
            "text": node.text,
            "x": round(node.transform.x, 3),
            "y": round(node.transform.y, 3),
            "w": round(node.transform.width, 3),
            "h": round(node.transform.height, 3),
            "parent": node.parent_id or "",
        }
        for page in context.document.pages
        for node in page.nodes.values()
        if node.visible and node.kind.value == "text"
    ]

    output = tmp_path / "semantic-pptx-probe"
    report = run_professional_probe(
        _REAL_SEMANTIC_TEMPLATE,
        output_dir=output,
        require_semantic_products=True,
    )

    metrics = dict(report.usability.get("metrics") or {})
    diagnostic = {
        "metrics": metrics,
        "gate_blockers": report.gate_blockers,
        "semantic_report": context.document.metadata.get("semantic_blocks"),
        "text_nodes": text_diagnostics,
    }
    assert metrics.get("price_blocks", 0) > 0, diagnostic
    assert metrics.get("product_cards", 0) > 0, diagnostic
    assert metrics.get("smart_slots", 0) > 0, diagnostic
    assert metrics.get("semantic_missing_members", 0) == 0, diagnostic
    assert metrics.get("semantic_missing_slots", 0) == 0, diagnostic
    assert metrics.get("duplicate_slot_ids", 0) == 0, diagnostic
    assert report.ready is True, report.to_dict()
    assert report.gate_blockers == []
    assert report.persistence_ok is True
    assert report.png_ok is True
    assert report.pdf_ok is True
