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
            count = self.session.delete_selected()
            return command_module.CommandResult(
                True,
                count > 0,
                f"{count} elemento(s) recortado(s)." if count else "Nada para recortar.",
                {"count": count},
            )
        if name == "paste":
            return _paste_clipboard(self, command, command_module)
        return original_dispatch(self, command)

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
