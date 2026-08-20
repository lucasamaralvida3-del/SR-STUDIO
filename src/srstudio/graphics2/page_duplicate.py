from __future__ import annotations

"""Clonagem de página com identidade nova para o SR Scene 2.

Duplicar um encarte não pode simplesmente copiar a árvore com ``deepcopy``.
Mesmo que nodes sejam escopados por página hoje, IDs repetidos tornam seleção,
semântica, persistência, telemetria e futuras operações cross-page ambíguas.

Este módulo preserva conteúdo e geometria, mas regenera as identidades locais
da página e remapeia referências conhecidas e metadados de forma recursiva.
"""

from collections.abc import Mapping
from typing import Any
import copy

from .model import GraphicsPage, _id


def clone_page_with_fresh_ids(source: GraphicsPage, *, name: str | None = None) -> GraphicsPage:
    """Retorna uma cópia visualmente idêntica com IDs internos exclusivos.

    São regenerados:
    - page id;
    - node ids;
    - SmartSlot ids;
    - semantic block ids presentes em ``page.metadata['semantic_blocks']``.

    Relações parent/children, roots, node_by_role, extra_bindings, metadados e
    estilos que apontam para essas identidades são remapeados. Assets continuam
    compartilhados porque pertencem ao documento e são imutáveis por identidade.
    """

    page = copy.deepcopy(source)
    new_page_id = _id("page")
    node_ids = {old_id: _id("node") for old_id in source.nodes}
    slot_ids = {old_id: _id("slot") for old_id in source.slots}
    block_ids = _semantic_block_id_map(source, slot_ids)

    identity_map: dict[str, str] = {source.id: new_page_id, **node_ids, **slot_ids, **block_ids}

    remapped_nodes = {}
    for old_id, node in page.nodes.items():
        new_id = node_ids[old_id]
        node.id = new_id
        node.parent_id = _mapped(node.parent_id, identity_map)
        node.children = [_mapped(child_id, identity_map) for child_id in node.children]
        node.style = _remap_nested(node.style, identity_map)
        node.metadata = _remap_nested(node.metadata, identity_map)
        remapped_nodes[new_id] = node

    remapped_slots = {}
    for old_id, slot in page.slots.items():
        new_id = slot_ids[old_id]
        slot.id = new_id
        slot.page_id = new_page_id
        slot.node_by_role = {
            str(role): _mapped(node_id, identity_map)
            for role, node_id in slot.node_by_role.items()
        }
        slot.metadata = _remap_nested(slot.metadata, identity_map)
        remapped_slots[new_id] = slot

    page.id = new_page_id
    page.name = name or f"{source.name} - cópia"
    page.nodes = remapped_nodes
    page.roots = [_mapped(node_id, identity_map) for node_id in page.roots]
    page.slots = remapped_slots
    page.metadata = _remap_nested(page.metadata, identity_map)

    return page


def install_safe_page_duplication(session_type: type) -> None:
    """Instala a implementação segura mantendo a API pública existente.

    A instalação ocorre no ``graphics2.__init__`` para preservar compatibilidade
    com callers existentes enquanto a API ``GraphicsSession.add_page`` continua
    com a mesma assinatura e sem exigir mudança no editor/QML.
    """

    if bool(getattr(session_type, "_sr_safe_page_duplicate_installed", False)):
        return

    def add_page(self, *, name: str | None = None, duplicate_active: bool = False) -> str:
        with self.transaction("Duplicar página" if duplicate_active else "Adicionar página"):
            if duplicate_active:
                page = clone_page_with_fresh_ids(self.page, name=name)
                self.document.pages.append(page)
                self.document.active_page_id = page.id
            else:
                self.document.add_page(GraphicsPage(name=name or f"Página {len(self.document.pages) + 1}"))
        self.clear_selection()
        return self.document.active_page_id

    session_type.add_page = add_page
    session_type._sr_safe_page_duplicate_installed = True


def _semantic_block_id_map(source: GraphicsPage, slot_ids: Mapping[str, str]) -> dict[str, str]:
    raw = source.metadata.get("semantic_blocks")
    if not isinstance(raw, dict):
        return {}

    result: dict[str, str] = {}
    for index, (raw_id, raw_block) in enumerate(raw.items()):
        old_id = str(raw_id)
        block = raw_block if isinstance(raw_block, dict) else {}
        kind = str(block.get("kind") or "").strip().lower()
        old_slot_id = str(block.get("slot_id") or "")
        new_slot_id = slot_ids.get(old_slot_id, "")

        if kind == "product_card" and new_slot_id:
            candidate = f"productcard:{new_slot_id}"
        elif kind == "price_block" and new_slot_id:
            suffix = _price_block_suffix(old_id, old_slot_id)
            candidate = f"priceblock:{new_slot_id}:{suffix}"
        elif kind == "product_card":
            candidate = f"productcard:duplicate:{_id('block')}"
        elif kind == "price_block":
            candidate = f"priceblock:duplicate:{_id('block')}"
        else:
            candidate = f"semantic:duplicate:{index}:{_id('block')}"
        result[old_id] = candidate
    return result


def _price_block_suffix(block_id: str, slot_id: str) -> str:
    prefix = f"priceblock:{slot_id}:"
    if slot_id and block_id.startswith(prefix):
        suffix = block_id[len(prefix):].strip()
        if suffix:
            return suffix
    if block_id.endswith(":app-price"):
        return "app-price"
    return "price"


def _mapped(value: str | None, identity_map: Mapping[str, str]) -> str | None:
    if value is None:
        return None
    return identity_map.get(str(value), str(value))


def _remap_nested(value: Any, identity_map: Mapping[str, str]) -> Any:
    """Remapeia IDs exatos inclusive quando aparecem como chaves de metadados."""

    if isinstance(value, str):
        return identity_map.get(value, value)
    if isinstance(value, dict):
        return {
            _remap_nested(key, identity_map): _remap_nested(item, identity_map)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_remap_nested(item, identity_map) for item in value]
    if isinstance(value, tuple):
        return tuple(_remap_nested(item, identity_map) for item in value)
    if isinstance(value, set):
        return {_remap_nested(item, identity_map) for item in value}
    return copy.deepcopy(value)
