from __future__ import annotations

from pathlib import Path

from srstudio.graphics2 import BindingRole, GraphicsDocument, GraphicsNode, GraphicsSession, NodeKind, Transform
from srstudio.graphics2.package import save_package
from srstudio.graphics2.professional_probe import run_professional_probe
from srstudio.graphics2.semantic_blocks import build_semantic_blocks


def _source_scene(tmp_path: Path) -> Path:
    session = GraphicsSession(GraphicsDocument(name="Probe Encarte"))
    page = session.page
    bindings = {}
    for role, text, x, y, width, height in [
        (BindingRole.NAME, "CAFÉ 500G", 100, 200, 300, 60),
        (BindingRole.CURRENCY, "R$", 100, 300, 45, 40),
        (BindingRole.PRICE_REAIS, "19", 145, 280, 100, 80),
        (BindingRole.PRICE_CENTS, ",90", 245, 290, 75, 45),
        (BindingRole.UNIT, "/UN", 250, 340, 70, 30),
    ]:
        node = GraphicsNode(
            kind=NodeKind.TEXT,
            text=text,
            name=role.value,
            binding_role=role,
            transform=Transform(x=x, y=y, width=width, height=height),
        )
        page.add_node(node)
        bindings[role] = node.id
    slot = session.create_slot("Café", bindings)
    session.bind_product(slot.id, {"id": "cafe", "display_name": "CAFÉ 500G", "price": "19,90", "unit": "UN"})
    build_semantic_blocks(session.document)
    return save_package(session.document, tmp_path / "source.srscene", embed_local_assets=False)


def test_professional_probe_validates_persistence_and_exports(tmp_path: Path):
    source = _source_scene(tmp_path)
    output = tmp_path / "probe-output"

    report = run_professional_probe(source, output_dir=output, require_bound_product=True)

    assert report.ready is True
    assert report.usability["ready"] is True
    assert report.persistence_ok is True
    assert report.png_ok is True
    assert report.pdf_ok is True
    assert report.page_count_before == report.page_count_after == 1
    assert report.node_count_before == report.node_count_after
    assert report.slot_count_before == report.slot_count_after == 1
    assert Path(report.scene_path).is_file()
    assert Path(report.png_path).is_file()
    assert Path(report.pdf_path).is_file()
    assert report.errors == []
