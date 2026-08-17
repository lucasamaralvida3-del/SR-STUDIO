from __future__ import annotations

"""Hardening one-to-one para identidade de imagens PPTX duplicadas.

``pptx_image_transform`` permanece a fonte de verdade para leitura e aplicação
exata de ``a:xfrm``. Esta camada só trata um caso conservador pós-prova: duas ou
mais imagens têm o mesmo nome, mas algumas já receberam ``pptx_shape_id`` por
uma evidência mais forte. Nodes comprovadamente pertencentes a outros shape IDs
são eliminados; o contrato restante só é aplicado quando sobra exatamente um
candidato sem conflito.

Não há pareamento por ordem, nome de arquivo ou campanha. Se ainda sobrarem dois
candidatos possíveis, o diagnóstico de ambiguidade permanece intacto.
"""

from pathlib import Path
from typing import Any

from .model import GraphicsDocument
from . import pptx_image_transform as base


def recover_pptx_image_transforms_professional(
    source: str | Path,
    document: GraphicsDocument,
):
    """Executa a prova base e resolve somente identidades restantes inequívocas."""

    path = Path(source)
    report = base.recover_pptx_image_transforms(path, document)
    ambiguous = [
        issue
        for issue in report.issues
        if issue.code == "PPTX_IMAGE_TRANSFORM_SHAPE_AMBIGUOUS"
    ]
    if not ambiguous:
        return report

    contracts = {
        (contract.slide, contract.shape_id, contract.shape_name): contract
        for contract in base._read_contracts(path)
    }
    resolved_issue_keys: set[tuple[int, str, str]] = set()

    for issue in ambiguous:
        key = (issue.slide, issue.shape_id, issue.shape_name)
        contract = contracts.get(key)
        if contract is None or contract.transformed_group_ancestor:
            continue
        if contract.slide <= 0 or contract.slide > len(document.pages):
            continue

        page = document.pages[contract.slide - 1]
        candidates = base._image_candidates(page.nodes.values(), contract.shape_name)
        eligible = [
            node
            for node in candidates
            if not str((node.metadata or {}).get("pptx_shape_id") or "")
            or str((node.metadata or {}).get("pptx_shape_id") or "") == contract.shape_id
        ]
        if len(eligible) != 1:
            continue

        node = eligible[0]
        previous = {
            "rotation": float(node.transform.rotation or 0.0),
            "flip_x": bool(node.style.get("flip_x")),
            "flip_y": bool(node.style.get("flip_y")),
        }
        changed = (
            not base._angle_equal(previous["rotation"], contract.rotation)
            or previous["flip_x"] != contract.flip_x
            or previous["flip_y"] != contract.flip_y
        )
        if changed:
            report.corrected_contracts += 1
            node.metadata["pptx_image_transform_previous"] = previous

        node.transform.rotation = float(contract.rotation)
        node.style["flip_x"] = bool(contract.flip_x)
        node.style["flip_y"] = bool(contract.flip_y)
        node.metadata["pptx_shape_id"] = contract.shape_id
        node.metadata["pptx_shape_name"] = contract.shape_name
        node.metadata["pptx_image_transform_match"] = "shape-id-elimination"
        node.metadata["pptx_image_transform"] = {
            "source_kind": contract.source_kind,
            "rotation": float(contract.rotation),
            "flip_x": bool(contract.flip_x),
            "flip_y": bool(contract.flip_y),
            "transformed_group_ancestor": False,
        }
        node.metadata["pptx_enhanced"] = True

        report.mapped_contracts += 1
        if hasattr(report, "identity_matches"):
            report.identity_matches += 1
        if base._node_matches(node, contract):
            report.exact_contracts += 1
            if contract.non_identity:
                report.exact_non_identity_contracts += 1
            resolved_issue_keys.add(key)

    if resolved_issue_keys:
        report.issues = [
            issue
            for issue in report.issues
            if (issue.slide, issue.shape_id, issue.shape_name) not in resolved_issue_keys
            or issue.code != "PPTX_IMAGE_TRANSFORM_SHAPE_AMBIGUOUS"
        ]

    document.metadata["pptx_image_transform_recovery"] = report.to_dict()
    return report
