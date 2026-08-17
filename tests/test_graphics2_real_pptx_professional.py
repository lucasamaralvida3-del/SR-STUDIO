from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.professional_probe import run_professional_probe
from srstudio.graphics2.qt_host import load_launch_context


_REPO_ROOT = Path(__file__).resolve().parents[1]
_REAL_CARTAZ_VENDA = _REPO_ROOT / "src" / "srstudio" / "assets" / "poster_templates" / "legacy" / "models" / "CARTAZ_VENDA.pptx"


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
    assert len(document.pages) >= 1

    nodes = [node for page in document.pages for node in page.nodes.values()]
    assert len(nodes) >= 4
    assert any(node.visible for node in nodes)
    assert any(node.visible and node.kind.value == "text" for node in nodes)

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
