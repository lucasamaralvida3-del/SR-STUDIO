from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from srstudio.graphics2.qt_host import load_launch_context
from srstudio.graphics2.usability_gate import inspect_encarte_usability


_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODELS = _REPO_ROOT / "src" / "srstudio" / "assets" / "poster_templates" / "legacy" / "models"
_AUDIT_PATH = _REPO_ROOT / "g2-real-corpus-audit.json"
_REAL_MODELS = (
    "ATACADO.pptx",
    "CARTAZ_VENDA.pptx",
    "CLUBE_EXCLUSIVO.pptx",
    "CLUBE_EXCLUSIVO_COM_LIMITE.pptx",
    "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx",
    "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx",
)


def _audit_payload(value: Any) -> Any:
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(value, dict):
        return dict(value)
    return str(value)


def test_real_sr_pptx_corpus_imports_with_structural_and_editability_safety():
    """Create a deterministic semantic/usability inventory for every real SR PPTX model."""

    cases: list[dict[str, object]] = []
    for filename in _REAL_MODELS:
        source = _MODELS / filename
        assert source.is_file(), f"Modelo real ausente: {filename}"
        context = load_launch_context(source)
        document = context.document
        graphics_gate = inspect_encarte_usability(document, require_semantic_products=False)
        semantic_gate = inspect_encarte_usability(document, require_semantic_products=True)
        semantic_report = dict(document.metadata.get("semantic_blocks") or {})
        named_slots = [
            slot
            for page in document.pages
            for slot in page.slots.values()
            if slot.metadata.get("explicit_named_semantics")
        ]
        recovered_slots = [
            slot
            for page in document.pages
            for slot in page.slots.values()
            if slot.metadata.get("semantic_recovered")
        ]
        text_names = sorted(
            {
                node.name
                for page in document.pages
                for node in page.nodes.values()
                if node.visible and node.kind.value == "text" and node.name
            }
        )
        cases.append(
            {
                "file": filename,
                "pages": len(document.pages),
                "graphics_ready": graphics_gate.ready,
                "semantic_ready": semantic_gate.ready,
                "graphics_metrics": graphics_gate.metrics,
                "semantic_metrics": semantic_gate.metrics,
                "semantic_blockers": [
                    {"code": item.code, "message": item.message}
                    for item in semantic_gate.checks
                    if not item.passed and item.severity == "blocker"
                ],
                "semantic_report": semantic_report,
                "explicit_named_slots": len(named_slots),
                "recovered_slots": len(recovered_slots),
                "import_audit": _audit_payload(context.import_audit),
                "text_names": text_names,
            }
        )

        assert graphics_gate.ready is True, {"file": filename, "gate": graphics_gate.to_dict()}
        assert graphics_gate.metrics.get("duplicate_page_ids", 0) == 0
        assert graphics_gate.metrics.get("duplicate_node_ids", 0) == 0
        assert graphics_gate.metrics.get("duplicate_slot_ids", 0) == 0
        assert graphics_gate.metrics.get("preflight_errors", 0) == 0
        assert graphics_gate.metrics.get("visible_nodes", 0) > 0
        assert graphics_gate.metrics.get("editable_nodes", 0) > 0

    payload = {
        "version": 1,
        "count": len(cases),
        "semantic_ready": sum(1 for case in cases if case["semantic_ready"]),
        "cases": cases,
    }
    _AUDIT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
