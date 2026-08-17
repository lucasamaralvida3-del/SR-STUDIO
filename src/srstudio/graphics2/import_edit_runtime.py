from __future__ import annotations

"""Pós-processamento profissional de importações para o Studio de Encartes/G2.

O bridge histórico preserva o layout marcando como bloqueado todo elemento que
não nasceu dentro de um SmartSlot. Isso é seguro para fidelidade, porém torna um
PPTX real praticamente somente-leitura. A camada profissional mantém formas
estruturais protegidas e libera apenas conteúdo que o operador precisa editar:
texto e imagem visíveis.

No mesmo ponto pós-importação também ativamos a prova exata de rotação/flip de
imagens DrawingML. O recuperador já existia no G2 e o Production Gate já conhecia
seu relatório, porém o caminho principal podia terminar sem executá-lo e então
parecer 100% coberto por ausência de contratos medidos. A recuperação continua
conservadora: ambiguidades ou transformações de grupo não são adivinhadas.

A política é aplicada somente ao resultado de ``GraphicsImportService``. Ela não
altera Golden Masters nem documentos já salvos que não passam por nova importação.
"""

from pathlib import Path
from typing import Any, Callable

from .import_audit import audit_import
from .model import GraphicsDocument, NodeKind
from .pptx_image_transform import recover_pptx_image_transforms
from .scene_fingerprint import store_scene_fingerprint


_EDITABLE_KINDS = {NodeKind.TEXT, NodeKind.IMAGE}
_STRUCTURAL_KINDS = {NodeKind.RECT, NodeKind.LINE, NodeKind.ELLIPSE, NodeKind.PATH}


def apply_import_editability(document: GraphicsDocument) -> dict[str, int | str]:
    """Libera conteúdo visual editável e preserva a estrutura do template."""

    unlocked_text = 0
    unlocked_images = 0
    protected_structural = 0
    already_editable = 0

    for page in document.pages:
        for node in page.nodes.values():
            if not node.visible or bool(node.metadata.get("template_hidden")):
                continue

            if node.kind in _EDITABLE_KINDS:
                if node.locked:
                    node.locked = False
                    if node.kind is NodeKind.TEXT:
                        unlocked_text += 1
                    else:
                        unlocked_images += 1
                else:
                    already_editable += 1
                node.metadata["import_editable"] = True
                node.metadata["import_editability_policy"] = "content-v1"
                continue

            if node.kind in _STRUCTURAL_KINDS and node.locked:
                protected_structural += 1

    report: dict[str, int | str] = {
        "version": 1,
        "policy": "content-v1",
        "unlocked_text": unlocked_text,
        "unlocked_images": unlocked_images,
        "already_editable": already_editable,
        "protected_structural": protected_structural,
    }
    document.metadata["import_editability"] = dict(report)
    return report


def _apply_pptx_image_transform_proof(source: Path, document: GraphicsDocument) -> None:
    """Mede/aplica contratos inequívocos de rotação/flip sem quebrar o import."""

    if source.suffix.lower() != ".pptx":
        return
    try:
        recover_pptx_image_transforms(source, document)
    except Exception as exc:
        # Importação continua utilizável, porém a falha deixa de ser mascarada
        # como cobertura perfeita. O Production Gate verá o erro explicitamente.
        document.metadata["pptx_image_transform_recovery"] = {
            "source_contracts": 0,
            "non_identity_contracts": 0,
            "mapped_contracts": 0,
            "exact_contracts": 0,
            "exact_non_identity_contracts": 0,
            "corrected_contracts": 0,
            "deferred_group_contracts": 0,
            "coverage": 0.0,
            "non_identity_coverage": 0.0,
            "issues": [],
            "error": str(exc),
        }


def _refresh_post_import_evidence(result: Any) -> None:
    """Mantém fingerprint/audit coerentes com as correções pós-importação."""

    fingerprint = store_scene_fingerprint(result.document)
    result.document.metadata["import_fingerprint_sha256"] = fingerprint.sha256
    result.audit = audit_import(result.document)


def install_import_editability_guard(import_module: Any) -> None:
    """Envolve ``GraphicsImportService.import_file`` uma única vez."""

    if bool(getattr(import_module, "_sr_import_editability_guard_installed", False)):
        return

    service = import_module.GraphicsImportService
    original: Callable[..., Any] = service.import_file

    def guarded_import(self: Any, *args: Any, **kwargs: Any):
        result = original(self, *args, **kwargs)
        raw_source = kwargs.get("path") if "path" in kwargs else (args[0] if args else "")
        source = Path(raw_source) if raw_source else Path()
        _apply_pptx_image_transform_proof(source, result.document)
        apply_import_editability(result.document)
        _refresh_post_import_evidence(result)
        return result

    guarded_import.__name__ = original.__name__
    guarded_import.__doc__ = original.__doc__
    guarded_import.__module__ = original.__module__
    import_module._sr_import_editability_original = original
    service.import_file = guarded_import
    import_module._sr_import_editability_guard_installed = True
