from __future__ import annotations

"""Hardening de comandos do editor G2 que não pertencem ao renderer/importador.

O Command Router é o contrato público do editor. Este runtime adiciona operações
multipágina e clipboard de produção sem reabrir o núcleo histórico em paralelo
com as outras frentes G2.
"""

from copy import deepcopy
from typing import Any

_SEMANTIC_METADATA_KEYS = {
    "semantic_product_card_id",
    "semantic_price_block_id",
    "semantic_block_id",
    "smart_slot_id",
    "slot_id",
    "slot_role",
}


def install_editor_commands(command_module: Any) -> None:
    """Instala comandos de editor preservando a API pública do router."""

    router_type = command_module.GraphicsCommandRouter
    if bool(getattr(router_type, "_sr_editor_commands_installed", False)):
        return

    original_dispatch = router_type.dispatch

    def dispatch(self, command: dict[str, Any]):
        name = str(command.get("name") or "").strip().lower()
        if name == "remove_page":
            return _remove_page(self, command, command_module)
        if name == "delete":
            count, blocked = _delete_selection_preserving_locks(self.session)
            if count:
                suffix = f" · {blocked} protegido(s) por bloqueio." if blocked else ""
                return command_module.CommandResult(
                    True,
                    True,
                    f"{count} elemento(s) excluído(s).{suffix}",
                    {"count": count, "blocked": blocked},
                )
            if blocked:
                return command_module.CommandResult(
                    True,
                    False,
                    "Seleção protegida por bloqueio; nada foi excluído.",
                    {"count": 0, "blocked": blocked},
                )
            return command_module.CommandResult(True, False, "Nada selecionado.", {"count": 0, "blocked": 0})
        if name in {"resize", "resize_handle", "edit_text"}:
            node_id = str(command.get("node_id") or self.session.anchor_id or "")
            if node_id and self.session.page.node(node_id) is not None and self.session.effective_locked(node_id):
                return command_module.CommandResult(
                    True,
                    False,
                    "Elemento bloqueado; alteração ignorada.",
                    {"node_id": node_id},
                )
        if name == "opacity":
            return _dispatch_editable_selection(self, command, command_module, original_dispatch, "Opacidade")
        if name == "layer":
            return _dispatch_editable_selection(self, command, command_module, original_dispatch, "Camada")
        if name == "ungroup":
            return _dispatch_editable_selection(self, command, command_module, original_dispatch, "Desagrupar")
        if name in {"copy", "cut"}:
            payload, error = _copy_selection(self)
            if error:
                return command_module.CommandResult(False, False, error)
            self._sr_editor_clipboard = payload
            self._sr_editor_paste_count = 0
            if name == "copy":
                return command_module.CommandResult(
                    True,
                    False,
                    f"{len(payload['roots'])} elemento(s) copiado(s).",
                    {"count": len(payload["roots"])},
                )
            count, blocked = _delete_selection_preserving_locks(self.session)
            if count:
                suffix = f" · {blocked} protegido(s) por bloqueio." if blocked else ""
                return command_module.CommandResult(
                    True,
                    True,
                    f"{count} elemento(s) recortado(s).{suffix}",
                    {"count": count, "blocked": blocked},
                )
            if blocked:
                return command_module.CommandResult(
                    True,
                    False,
                    "Elemento(s) bloqueado(s) foram copiados para o clipboard, mas não removidos.",
                    {"count": 0, "blocked": blocked},
                )
            return command_module.CommandResult(True, False, "Nada para recortar.", {"count": 0, "blocked": 0})
        if name == "paste":
            return _paste_clipboard(self, command, command_module)

        result = original_dispatch(self, command)
        if name == "reorder_page" and result.ok and result.changed:
            # Reordenar outra página também a torna ativa no router histórico.
            # A seleção antiga pertence à página anterior e não pode sobreviver
            # como IDs órfãos para o próximo move/delete/atalho.
            self.session.clear_selection()
        return result

    router_type.dispatch = dispatch
    router_type._sr_editor_commands_installed = True


def _remove_page(self: Any, command: dict[str, Any], command_module: Any):
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


def _delete_selection_preserving_locks(session: Any) -> tuple[int, int]:
    page = session.page
    selected = {node_id for node_id in session.selection if node_id in page.nodes}
    if not selected:
        return 0, 0

    roots: list[str] = []
    for node_id in selected:
        parent_id = page.nodes[node_id].parent_id
        has_selected_ancestor = False
        guard = 0
        while parent_id and parent_id in page.nodes and guard < 128:
            if parent_id in selected:
                has_selected_ancestor = True
                break
            parent_id = page.nodes[parent_id].parent_id
            guard += 1
        if not has_selected_ancestor:
            roots.append(node_id)

    editable_roots: list[str] = []
    blocked_roots: list[str] = []
    for root_id in roots:
        tree_ids = [root_id, *page.descendants(root_id)]
        if any(session.effective_locked(node_id) for node_id in tree_ids):
            blocked_roots.append(root_id)
        else:
            editable_roots.append(root_id)

    if not editable_roots:
        return 0, len(blocked_roots)

    original_selection = set(session.selection)
    original_anchor = session.anchor_id
    session.selection = set(editable_roots)
    session.anchor_id = editable_roots[-1] if editable_roots else None
    count = session.delete_selected()
    remaining = {node_id for node_id in original_selection if node_id in session.page.nodes}
    session.selection = remaining
    session.anchor_id = original_anchor if original_anchor in remaining else next(iter(remaining), None)
    return count, len(blocked_roots)


def _dispatch_editable_selection(
    self: Any,
    command: dict[str, Any],
    command_module: Any,
    original_dispatch: Any,
    label: str,
):
    session = self.session
    page = session.page
    original_selection = {node_id for node_id in session.selection if node_id in page.nodes}
    if not original_selection:
        return original_dispatch(self, command)
    editable = {node_id for node_id in original_selection if not session.effective_locked(node_id)}
    blocked_ids = original_selection - editable
    blocked = len(blocked_ids)
    if not blocked:
        return original_dispatch(self, command)
    if not editable:
        return command_module.CommandResult(
            True,
            False,
            f"{label}: seleção protegida por bloqueio; nenhuma alteração aplicada.",
            {"blocked": blocked},
        )

    original_anchor = session.anchor_id
    session.selection = editable
    session.anchor_id = original_anchor if original_anchor in editable else next(iter(editable), None)
    post_selection: set[str] = set()
    post_anchor: str | None = None
    try:
        result = original_dispatch(self, command)
        post_selection = {node_id for node_id in session.selection if node_id in session.page.nodes}
        post_anchor = session.anchor_id
    finally:
        blocked_remaining = {node_id for node_id in blocked_ids if node_id in session.page.nodes}
        restored = post_selection | blocked_remaining
        session.selection = restored
        if post_anchor in restored:
            session.anchor_id = post_anchor
        elif original_anchor in restored:
            session.anchor_id = original_anchor
        else:
            session.anchor_id = next(iter(restored), None)
    if result.ok:
        result.payload = dict(result.payload or {})
        result.payload["blocked"] = blocked
        result.message = f"{result.message} {blocked} elemento(s) bloqueado(s) preservado(s).".strip()
    return result


def _copy_selection(self: Any) -> tuple[dict[str, Any], str]:
    page = self.session.page
    selected = {node_id for node_id in self.session.selection if node_id in page.nodes}
    if not selected:
        return {}, "Nada selecionado para copiar."

    root_ids: list[str] = []
    for node_id in sorted(selected, key=lambda value: (page.nodes[value].z_index, value)):
        parent_id = page.nodes[node_id].parent_id
        ancestor_selected = False
        guard = 0
        while parent_id and parent_id in page.nodes and guard < 128:
            if parent_id in selected:
                ancestor_selected = True
                break
            parent_id = page.nodes[parent_id].parent_id
            guard += 1
        if not ancestor_selected:
            root_ids.append(node_id)

    copied_ids: set[str] = set()
    for root_id in root_ids:
        copied_ids.add(root_id)
        copied_ids.update(page.descendants(root_id))

    semantic_nodes = []
    for node_id in copied_ids:
        node = page.nodes[node_id]
        metadata = node.metadata if isinstance(node.metadata, dict) else {}
        if node.binding_role is not None or any(key in metadata for key in _SEMANTIC_METADATA_KEYS):
            semantic_nodes.append(node_id)
    if semantic_nodes:
        return {}, (
            "Clipboard comum não duplica ProductCard/PriceBlock/Smart Slot. "
            "Use Duplicar para manter a semântica do card."
        )

    return {
        "roots": root_ids,
        "nodes": {node_id: deepcopy(page.nodes[node_id]) for node_id in copied_ids},
    }, ""


def _paste_clipboard(self: Any, command: dict[str, Any], command_module: Any):
    clipboard = getattr(self, "_sr_editor_clipboard", None)
    if not isinstance(clipboard, dict) or not clipboard.get("nodes"):
        return command_module.CommandResult(True, False, "Clipboard vazio.")

    page = self.session.page
    source_nodes = dict(clipboard["nodes"])
    roots = [str(node_id) for node_id in clipboard.get("roots") or [] if node_id in source_nodes]
    paste_count = int(getattr(self, "_sr_editor_paste_count", 0)) + 1
    base_dx = float(command.get("dx") if command.get("dx") is not None else 20.0)
    base_dy = float(command.get("dy") if command.get("dy") is not None else 20.0)
    dx = base_dx * paste_count
    dy = base_dy * paste_count
    mapping: dict[str, str] = {}
    clones: dict[str, Any] = {}

    for old_id, source in source_nodes.items():
        clone = source.clone()
        mapping[str(old_id)] = clone.id
        clones[str(old_id)] = clone

    with self.session.transaction("Colar elementos"):
        for old_id, source in source_nodes.items():
            old_key = str(old_id)
            clone = clones[old_key]
            clone.parent_id = mapping.get(str(source.parent_id or "")) or None
            clone.children = [mapping[str(child)] for child in source.children if str(child) in mapping]
            clone.transform.x += dx
            clone.transform.y += dy
            clone.z_index += paste_count
            page.nodes[clone.id] = clone
        for old_root in roots:
            new_root = mapping.get(old_root)
            if new_root and new_root not in page.roots:
                page.roots.append(new_root)

    created = [mapping[root] for root in roots if root in mapping]
    self.session.selection = set(created)
    self.session.anchor_id = created[-1] if created else None
    self._sr_editor_paste_count = paste_count
    return command_module.CommandResult(
        True,
        bool(created),
        f"{len(created)} elemento(s) colado(s)." if created else "Nada para colar.",
        {"node_ids": created},
    )
