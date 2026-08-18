from __future__ import annotations

"""Hardening de comandos do editor G2 que não pertencem ao renderer/importador.

O Command Router é o contrato público do editor. Este runtime adiciona operações
multipágina de produção sem reabrir o núcleo histórico em paralelo com as outras
frentes G2.
"""

from typing import Any


def install_editor_commands(command_module: Any) -> None:
    """Instala comandos de editor preservando a API pública do router.

    Atualmente adiciona ``remove_page`` com as seguintes garantias:
    - nunca deixa o documento sem páginas;
    - escolhe deterministicamente a página vizinha após a remoção;
    - participa de undo/redo pela transação do ``GraphicsSession``;
    - limpa seleção para impedir IDs da página removida escaparem para a UI.
    """

    router_type = command_module.GraphicsCommandRouter
    if bool(getattr(router_type, "_sr_editor_commands_installed", False)):
        return

    original_dispatch = router_type.dispatch

    def dispatch(self, command: dict[str, Any]):
        name = str(command.get("name") or "").strip().lower()
        if name != "remove_page":
            return original_dispatch(self, command)

        document = self.session.document
        if len(document.pages) <= 1:
            return command_module.CommandResult(
                True,
                False,
                "O projeto precisa manter pelo menos uma página.",
                {"page_id": document.active_page_id, "page_count": len(document.pages)},
            )

        page_id = str(command.get("page_id") or document.active_page_id or "")
        index = next((i for i, page in enumerate(document.pages) if page.id == page_id), -1)
        if index < 0:
            return command_module.CommandResult(False, False, "Página inexistente.")

        removed_name = document.pages[index].name
        with self.session.transaction("Remover página"):
            document.pages.pop(index)
            next_index = min(index, len(document.pages) - 1)
            document.active_page_id = document.pages[next_index].id

        self.session.clear_selection()
        return command_module.CommandResult(
            True,
            True,
            f"Página removida: {removed_name}.",
            {
                "removed_page_id": page_id,
                "page_id": document.active_page_id,
                "page_count": len(document.pages),
            },
        )

    router_type.dispatch = dispatch
    router_type._sr_editor_commands_installed = True
