from __future__ import annotations

"""Política de editabilidade pós-importação para o Studio de Encartes/G2.

O bridge histórico preserva o layout marcando como bloqueado todo elemento que
não nasceu dentro de um SmartSlot. Isso é seguro para fidelidade, porém torna um
PPTX real praticamente somente-leitura. A camada profissional mantém formas
estruturais protegidas e libera apenas conteúdo que o operador precisa editar:
texto e imagem visíveis.

A política é aplicada somente ao resultado de ``GraphicsImportService``. Ela não
muda geometria, z-order, bindings, Golden Masters ou documentos já salvos que
não passam por uma nova importação.
"""

from typing import Any, Callable

from .model import GraphicsDocument, NodeKind


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


def install_import_editability_guard(import_module: Any) -> None:
    """Envolve ``GraphicsImportService.import_file`` uma única vez."""

    if bool(getattr(import_module, "_sr_import_editability_guard_installed", False)):
        return

    service = import_module.GraphicsImportService
    original: Callable[..., Any] = service.import_file

    def guarded_import(self: Any, *args: Any, **kwargs: Any):
        result = original(self, *args, **kwargs)
        apply_import_editability(result.document)
        return result

    guarded_import.__name__ = original.__name__
    guarded_import.__doc__ = original.__doc__
    guarded_import.__module__ = original.__module__
    import_module._sr_import_editability_original = original
    service.import_file = guarded_import
    import_module._sr_import_editability_guard_installed = True
