from __future__ import annotations

"""Proteções de runtime para semântica recuperada do Studio de Encartes.

O recuperador histórico cria SmartSlots determinísticos a partir do conteúdo do
card. Isso é desejável dentro de uma página, mas duas páginas clonadas podem
produzir o mesmo ID. Além disso, a reconstrução remove slots inferidos antes de
criá-los novamente, o que pode apagar o vínculo de produto feito pelo usuário.

Esta camada mantém o algoritmo visual/recovery original intacto e adiciona duas
invariantes de documento:

1. identidades recuperadas não colidem entre páginas;
2. estado de produto/lock de um slot recuperado sobrevive a rebuild idempotente.

Nenhuma geometria, texto ou regra de detecção é alterada aqui.
"""

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Callable

from .model import GraphicsDocument, GraphicsPage, SmartSlot
from .semantic_price_runtime import install_complete_price_recovery_guard


@dataclass(slots=True)
class _RecoveredSlotState:
    product_id: str
    locked: bool
    product_snapshot: Any


def install_semantic_recovery_guard(semantic_module: Any) -> None:
    """Envolve ``build_semantic_blocks`` uma única vez com invariantes globais."""

    # O builder histórico resolve `_recover_unbound_price_blocks` pelo namespace
    # do módulo a cada chamada. Instalar primeiro a extensão de preço completo
    # mantém o caminho split legado intacto e o inclui dentro do mesmo guard de
    # identidade/persistência.
    install_complete_price_recovery_guard(semantic_module)

    if bool(getattr(semantic_module, "_sr_semantic_recovery_guard_installed", False)):
        return

    original: Callable[..., Any] = semantic_module.build_semantic_blocks

    def guarded_build(document: GraphicsDocument, *args: Any, **kwargs: Any):
        recovered_state = _capture_recovered_slot_state(document)
        report = original(document, *args, **kwargs)
        _normalize_document_recovered_identities(document)
        _restore_recovered_slot_state(document, recovered_state)
        return report

    guarded_build.__name__ = original.__name__
    guarded_build.__doc__ = original.__doc__
    guarded_build.__module__ = original.__module__
    semantic_module._sr_semantic_original_builder = original
    semantic_module.build_semantic_blocks = guarded_build
    semantic_module._sr_semantic_recovery_guard_installed = True


def _capture_recovered_slot_state(
    document: GraphicsDocument,
) -> dict[str, dict[str, _RecoveredSlotState]]:
    state: dict[str, dict[str, _RecoveredSlotState]] = {}
    for page in document.pages:
        page_state: dict[str, _RecoveredSlotState] = {}
        for slot in page.slots.values():
            if not _is_recovered(slot):
                continue
            key = _slot_semantic_key(slot)
            page_state[key] = _RecoveredSlotState(
                product_id=str(slot.product_id or ""),
                locked=bool(slot.locked),
                product_snapshot=deepcopy(slot.metadata.get("product_snapshot")),
            )
        if page_state:
            state[page.id] = page_state
    return state


def _restore_recovered_slot_state(
    document: GraphicsDocument,
    captured: Mapping[str, Mapping[str, _RecoveredSlotState]],
) -> None:
    for page in document.pages:
        page_state = captured.get(page.id)
        if not page_state:
            continue
        for slot in page.slots.values():
            if not _is_recovered(slot):
                continue
            previous = page_state.get(_slot_semantic_key(slot))
            if previous is None:
                continue
            slot.product_id = previous.product_id
            slot.locked = previous.locked
            if previous.product_snapshot not in (None, {}):
                slot.metadata["product_snapshot"] = deepcopy(previous.product_snapshot)


def _normalize_document_recovered_identities(document: GraphicsDocument) -> None:
    """Escopa somente IDs que realmente colidem entre páginas.

    Um projeto de página única mantém os IDs legados, preservando compatibilidade
    e snapshots históricos. Quando o mesmo ID aparece em páginas diferentes,
    todas as ocorrências conflitantes recebem um sufixo estável derivado do ID
    da página. Rebuilds seguintes produzem o mesmo resultado.
    """

    slot_occurrences: dict[str, list[GraphicsPage]] = defaultdict(list)
    block_occurrences: dict[str, list[GraphicsPage]] = defaultdict(list)

    for page in document.pages:
        for slot_id, slot in page.slots.items():
            if _is_recovered(slot):
                slot_occurrences[str(slot_id)].append(page)
        blocks = page.metadata.get("semantic_blocks")
        if isinstance(blocks, dict):
            for block_id, raw in blocks.items():
                if _is_recovered_block(raw):
                    block_occurrences[str(block_id)].append(page)

    slot_renames: dict[str, dict[str, str]] = defaultdict(dict)
    block_renames: dict[str, dict[str, str]] = defaultdict(dict)

    for old_id, pages in slot_occurrences.items():
        unique_pages = _unique_pages(pages)
        if len(unique_pages) <= 1:
            continue
        for page in unique_pages:
            slot_renames[page.id][old_id] = _scoped_identity(old_id, page.id)

    for old_id, pages in block_occurrences.items():
        unique_pages = _unique_pages(pages)
        if len(unique_pages) <= 1:
            continue
        for page in unique_pages:
            block_renames[page.id][old_id] = _scoped_identity(old_id, page.id)

    for page in document.pages:
        identity_map = {
            **slot_renames.get(page.id, {}),
            **block_renames.get(page.id, {}),
        }
        if identity_map:
            _apply_page_identity_map(page, identity_map)


def _apply_page_identity_map(page: GraphicsPage, identity_map: Mapping[str, str]) -> None:
    remapped_slots: dict[str, SmartSlot] = {}
    for old_id, slot in page.slots.items():
        new_id = identity_map.get(str(old_id), str(old_id))
        slot.id = new_id
        slot.metadata = _remap_nested(slot.metadata, identity_map)
        remapped_slots[new_id] = slot
    page.slots = remapped_slots

    for node in page.nodes.values():
        node.metadata = _remap_nested(node.metadata, identity_map)
        node.style = _remap_nested(node.style, identity_map)

    page.metadata = _remap_nested(page.metadata, identity_map)


def _is_recovered(slot: SmartSlot) -> bool:
    return bool(slot.metadata.get("semantic_recovered"))


def _is_recovered_block(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    metadata = raw.get("metadata")
    if isinstance(metadata, dict) and bool(metadata.get("recovered")):
        return True
    block_id = str(raw.get("id") or "")
    return ":recovered:" in block_id


def _slot_semantic_key(slot: SmartSlot) -> str:
    group_id = str(slot.metadata.get("source_group_id") or "").strip()
    if group_id:
        return f"group:{group_id}"
    bindings = "|".join(
        f"{str(role)}={str(node_id)}"
        for role, node_id in sorted(slot.node_by_role.items(), key=lambda item: str(item[0]))
    )
    if bindings:
        return f"nodes:{bindings}"
    return f"slot:{_unscoped_identity(slot.id)}"


def _unscoped_identity(value: str) -> str:
    marker = ":page-"
    text = str(value)
    index = text.rfind(marker)
    return text[:index] if index >= 0 else text


def _scoped_identity(value: str, page_id: str) -> str:
    base = _unscoped_identity(value)
    digest = sha1(str(page_id).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"{base}:page-{digest}"


def _unique_pages(pages: list[GraphicsPage]) -> list[GraphicsPage]:
    seen: set[str] = set()
    output: list[GraphicsPage] = []
    for page in pages:
        if page.id in seen:
            continue
        seen.add(page.id)
        output.append(page)
    return output


def _remap_nested(value: Any, identity_map: Mapping[str, str]) -> Any:
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
    return value
