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
        transform_report = dict(document.metadata.get("pptx_image_transform_recovery") or {})
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
                "image_transform_recovery": transform_report,
                "image_transform_metrics": {
                    "source_contracts": int(transform_report.get("source_contracts", 0) or 0),
                    "non_identity_contracts": int(transform_report.get("non_identity_contracts", 0) or 0),
                    "mapped_contracts": int(transform_report.get("mapped_contracts", 0) or 0),
                    "exact_contracts": int(transform_report.get("exact_contracts", 0) or 0),
                    "exact_non_identity_contracts": int(
                        transform_report.get("exact_non_identity_contracts", 0) or 0
                    ),
                    "deferred_group_contracts": int(transform_report.get("deferred_group_contracts", 0) or 0),
                    "coverage": float(transform_report.get("coverage", 1.0) or 0.0),
                    "non_identity_coverage": float(
                        transform_report.get("non_identity_coverage", 1.0) or 0.0
                    ),
                    "error": str(transform_report.get("error") or ""),
                },
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
        assert "error" not in transform_report, {
            "file": filename,
            "image_transform_recovery": transform_report,
        }

    payload = {
        "version": 2,
        "count": len(cases),
        "semantic_ready": sum(1 for case in cases if case["semantic_ready"]),
        "image_transform_totals": {
            "source_contracts": sum(
                int(case["image_transform_metrics"]["source_contracts"]) for case in cases
            ),
            "non_identity_contracts": sum(
                int(case["image_transform_metrics"]["non_identity_contracts"]) for case in cases
            ),
            "exact_contracts": sum(
                int(case["image_transform_metrics"]["exact_contracts"]) for case in cases
            ),
            "exact_non_identity_contracts": sum(
                int(case["image_transform_metrics"]["exact_non_identity_contracts"]) for case in cases
            ),
            "deferred_group_contracts": sum(
                int(case["image_transform_metrics"]["deferred_group_contracts"]) for case in cases
            ),
        },
        "cases": cases,
    }
    _AUDIT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
