from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import copy
import json

from .drop_target import find_drop_target
from .geometry import SnapEngine, SnapSettings
from .id_repair import repair_legacy_cross_page_ids
from .image_replace import replace_image_source
from .import_bridge import CanvaBindingService
from .model import GraphicsNode, NodeKind, Transform, _id
from .operations import GraphicsSession
from .semantic_blocks import semantic_block, semantic_member_ids, semantic_owner
from .smart_slot_manual import (
    mark_slot_non_product,
    merge_slot_manually,
    restore_auto_slot_bounds,
    set_manual_slot_bounds,
    snap_bounds_to_grid,
)


@dataclass(slots=True)
class CommandResult:
    ok: bool
    changed: bool = False
    message: str = ""
    payload: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "changed": self.changed, "message": self.message, "payload": self.payload or {}}


class GraphicsCommandRouter:
    """Contrato de comandos único para UI, atalhos, SR IA e automações."""

    def __init__(self, session: GraphicsSession) -> None:
        self.session = session
        # Open-time migration is deliberately outside the undo stack.
        self.integrity_repair = repair_legacy_cross_page_ids(self.session.document)
        self.snap = SnapSettings()
        self._clipboard: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        scene = self.session.document.to_dict()
        page = self.session.page
        selected = set(self.session.selection)
        page_index = [item["id"] for item in scene["pages"]].index(page.id)
        for node in scene["pages"][page_index]["nodes"].values():
            node["selected"] = node["id"] in selected
        scene["editor"] = {
            "selection": sorted(selected),
            "anchor_id": self.session.anchor_id or "",
            "can_undo": self.session.history.can_undo,
            "can_redo": self.session.history.can_redo,
            "undo_label": self.session.history.undo_label,
            "redo_label": self.session.history.redo_label,
            "clipboard_available": bool(self._clipboard),
            "snap": asdict(self.snap),
            "products": list(self.session.document.metadata.get("products") or []),
            "integrity_repair": self.integrity_repair.to_dict(),
        }
        return scene

    def dispatch_json(self, raw: str, *, include_scene_payload: bool = True) -> str:
        try:
            command = json.loads(raw)
            if not isinstance(command, dict):
                raise ValueError("Comando JSON deve ser um objeto.")
            result = self.dispatch(command)
        except Exception as exc:
            result = CommandResult(False, False, f"Erro: {exc}")
        # QML already receives sceneJson through sceneChanged. Serializing the full
        # document again into every command response doubles release-path work and
        # used to discard command-specific payloads such as Smart Slot bounds.
        if include_scene_payload:
            result.payload = self.payload()
        return json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def dispatch(self, command: dict[str, Any]) -> CommandResult:
        name = str(command.get("name") or "").strip().lower()
        if not name:
            return CommandResult(False, False, "Comando vazio.")
        try:
            if name == "select":
                node_id = str(command.get("node_id") or "")
                if not node_id:
                    return CommandResult(False, False, "node_id ausente.")
                if self.session.page.node(node_id) is None:
                    return CommandResult(False, False, "Elemento inexistente.")
                semantic = bool(command.get("semantic", False))
                scope = str(command.get("semantic_scope") or ("auto" if semantic else "node")).lower()
                node_ids, block_id = self._selection_target(node_id, scope)
                self._apply_selection(
                    node_ids,
                    anchor_id=node_id,
                    additive=bool(command.get("additive", False)),
                    toggle=bool(command.get("toggle", False)),
                )
                block = semantic_block(self.session.page, block_id) if block_id else None
                kind = str(block.get("kind") or "") if block else ""
                message = "PriceBlock selecionado." if kind == "price_block" else "ProductCard selecionado." if kind == "product_card" else "Seleção atualizada."
                return CommandResult(
                    True,
                    False,
                    message,
                    {"selection": sorted(self.session.selection), "semantic_block_id": block_id, "semantic_kind": kind},
                )
            if name == "clear_selection":
                self.session.clear_selection()
                return CommandResult(True, False, "Seleção limpa.")
            if name == "move":
                dx = float(command.get("dx") or 0); dy = float(command.get("dy") or 0)
                if not self.session.selection:
                    return CommandResult(True, False, "Nada selecionado.")
                if bool(command.get("snap", True)):
                    result = SnapEngine.snap_move(self.session.page, self.session.selection, dx, dy, zoom=float(command.get("zoom") or 1.0), settings=self.snap)
                    dx, dy = result.dx, result.dy
                    guides = {"x": result.guide_x, "y": result.guide_y, "source_x": result.source_x, "source_y": result.source_y}
                else:
                    guides = {}
                self.session.move_selected(dx, dy, clamp=bool(command.get("clamp", False)))
                return CommandResult(True, bool(dx or dy), "Elementos movidos.", {"guides": guides})
            if name == "resize":
                node_id = str(command.get("node_id") or self.session.anchor_id or "")
                if not node_id:
                    return CommandResult(False, False, "Nenhum elemento selecionado.")
                if self.session.page.node(node_id) is None:
                    return CommandResult(False, False, "Elemento inexistente.")
                self.session.resize_node(node_id, x=_optional_float(command, "x"), y=_optional_float(command, "y"), width=_optional_float(command, "width"), height=_optional_float(command, "height"), min_size=float(command.get("min_size") or 1.0))
                return CommandResult(True, True, "Elemento redimensionado.")
            if name == "resize_handle":
                return self._resize_handle(command)
            if name == "rotate":
                self.session.rotate_selected(float(command.get("angle") or 0), relative=bool(command.get("relative", False)), snap=_optional_float(command, "snap"))
                return CommandResult(True, bool(self.session.selection), "Rotação aplicada.")
            if name == "opacity":
                self.session.set_opacity(float(command.get("value", 1.0)))
                return CommandResult(True, bool(self.session.selection), "Opacidade atualizada.")
            if name == "lock":
                self.session.lock_selected(bool(command.get("value", True)))
                return CommandResult(True, bool(self.session.selection), "Bloqueio atualizado.")
            if name == "hide":
                self.session.hide_selected(bool(command.get("value", True)))
                return CommandResult(True, bool(self.session.selection), "Visibilidade atualizada.")
            if name == "layer":
                self.session.layer_selected(str(command.get("mode") or "front"))
                return CommandResult(True, bool(self.session.selection), "Camada atualizada.")
            if name == "align":
                self.session.align_selected(str(command.get("mode") or "left"))
                return CommandResult(True, len(self.session.selection) >= 2, "Alinhamento aplicado.")
            if name == "distribute":
                self.session.distribute_selected(str(command.get("axis") or "horizontal"))
                return CommandResult(True, len(self.session.selection) >= 3, "Distribuição aplicada.")
            if name == "group":
                group_id = self.session.group_selected(str(command.get("name_value") or "Grupo"))
                return CommandResult(True, bool(group_id), "Elementos agrupados." if group_id else "Selecione dois ou mais elementos.", {"group_id": group_id})
            if name == "ungroup":
                count = self.session.ungroup_selected()
                return CommandResult(True, count > 0, "Grupo desfeito." if count else "Nenhum grupo selecionado.", {"count": count})
            if name == "duplicate":
                created, slot_ids = self._duplicate_selected_with_semantics(
                    float(command.get("dx") or 20.0),
                    float(command.get("dy") or 20.0),
                )
                return CommandResult(
                    True,
                    bool(created),
                    "Elementos duplicados." if created else "Nada para duplicar.",
                    {"node_ids": created, "slot_ids": slot_ids},
                )
            if name == "copy":
                count = self._copy_selection()
                return CommandResult(
                    True,
                    False,
                    f"{count} elemento(s) copiado(s)." if count else "Nada selecionado para copiar.",
                    {"count": count, "clipboard_available": bool(self._clipboard)},
                )
            if name == "paste":
                if not self._clipboard:
                    return CommandResult(False, False, "A área de transferência está vazia.")
                dx = 20.0 if command.get("dx") in (None, "") else float(command["dx"])
                dy = 20.0 if command.get("dy") in (None, "") else float(command["dy"])
                created, slot_ids = self._paste_clipboard(dx, dy)
                return CommandResult(
                    True,
                    bool(created),
                    "Elementos colados." if created else "Nada para colar.",
                    {"node_ids": created, "slot_ids": slot_ids},
                )
            if name == "delete":
                count = self.session.delete_selected()
                return CommandResult(True, count > 0, "Elementos excluídos." if count else "Nada selecionado.", {"count": count})
            if name == "edit_text":
                node_id = str(command.get("node_id") or self.session.anchor_id or "")
                self.session.set_text(node_id, str(command.get("text") or ""))
                return CommandResult(True, bool(node_id), "Texto atualizado.")
            if name == "add_text":
                node = self.session.add_text(str(command.get("text") or "Texto"), x=float(command.get("x") or 0), y=float(command.get("y") or 0), width=float(command.get("width") or 220), height=float(command.get("height") or 60), name=str(command.get("name_value") or "Texto"))
                return CommandResult(True, True, "Texto adicionado.", {"node_id": node.id})
            if name == "add_rect":
                node = GraphicsNode(kind=NodeKind.RECT, name=str(command.get("name_value") or "Retângulo"), transform=Transform(x=float(command.get("x") or 0), y=float(command.get("y") or 0), width=float(command.get("width") or 180), height=float(command.get("height") or 120)), style={"fill": str(command.get("fill") or "#FFFFFF"), "stroke": str(command.get("stroke") or "transparent"), "stroke_width": float(command.get("stroke_width") or 0), "radius": float(command.get("radius") or 0)})
                self.session.add_node(node, label="Adicionar forma")
                return CommandResult(True, True, "Forma adicionada.", {"node_id": node.id})
            if name == "crop":
                node_id = str(command.get("node_id") or self.session.anchor_id or "")
                node = self.session.page.node(node_id)
                if node is None or node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
                    return CommandResult(False, False, "Selecione uma imagem editável.")
                if self.session.effective_locked(node_id):
                    return CommandResult(False, False, "A imagem está bloqueada.")
                self.session.set_image_crop(
                    node_id,
                    fit=str(command["fit"]) if "fit" in command else None,
                    focus_x=_optional_float(command, "focus_x"),
                    focus_y=_optional_float(command, "focus_y"),
                    zoom=_optional_float(command, "zoom"),
                    flip_x=_optional_bool(command, "flip_x"),
                    flip_y=_optional_bool(command, "flip_y"),
                    crop_left=_optional_float(command, "crop_left"),
                    crop_top=_optional_float(command, "crop_top"),
                    crop_right=_optional_float(command, "crop_right"),
                    crop_bottom=_optional_float(command, "crop_bottom"),
                    crop_reset=bool(command.get("crop_reset", False)),
                )
                return CommandResult(True, True, "Enquadramento e crop atualizados.", {"node_id": node_id})
            if name == "replace_image":
                node_id = str(command.get("node_id") or self.session.anchor_id or "")
                if not node_id:
                    return CommandResult(False, False, "Nenhuma imagem selecionada.")
                replacement = replace_image_source(
                    self.session,
                    node_id,
                    str(command.get("source") or ""),
                )
                return CommandResult(
                    True,
                    True,
                    "Imagem substituída.",
                    {
                        "node_id": replacement.node_id,
                        "asset_id": replacement.asset_id,
                        "source": replacement.source,
                        "reused_asset": replacement.reused_asset,
                    },
                )
            if name in {"add_page", "duplicate_page"}:
                page_id = self.session.add_page(name=str(command.get("name_value") or "") or None, duplicate_active=name == "duplicate_page")
                return CommandResult(True, True, "Página criada.", {"page_id": page_id})
            if name == "select_page":
                page_id = str(command.get("page_id") or "")
                if self.session.document.page(page_id) is None:
                    return CommandResult(False, False, "Página inexistente.")
                self.session.document.active_page_id = page_id; self.session.clear_selection()
                return CommandResult(True, False, "Página selecionada.")
            if name == "delete_page":
                document = self.session.document
                if len(document.pages) <= 1:
                    return CommandResult(False, False, "O projeto precisa manter pelo menos uma página.")
                page_id = str(command.get("page_id") or document.active_page_id or "")
                page_index = next((index for index, page in enumerate(document.pages) if page.id == page_id), -1)
                if page_index < 0:
                    return CommandResult(False, False, "Página inexistente.")
                with self.session.transaction("Excluir página"):
                    document.pages.pop(page_index)
                    if document.active_page_id == page_id:
                        next_index = min(page_index, len(document.pages) - 1)
                        document.active_page_id = document.pages[next_index].id
                self.session.clear_selection()
                return CommandResult(
                    True,
                    True,
                    "Página excluída.",
                    {
                        "page_id": page_id,
                        "active_page_id": document.active_page_id,
                        "page_ids": [page.id for page in document.pages],
                    },
                )
            if name == "reorder_page":
                document = self.session.document
                pages = document.pages
                if len(pages) < 2:
                    return CommandResult(True, False, "Há somente uma página.")
                page_id = str(command.get("page_id") or document.active_page_id or "")
                current_index = next((index for index, item in enumerate(pages) if item.id == page_id), -1)
                if current_index < 0:
                    return CommandResult(False, False, "Página inexistente.")
                mode = str(command.get("mode") or "").strip().lower()
                if "target_index" in command or "index" in command:
                    raw_index = command.get("target_index", command.get("index"))
                    target_index = int(raw_index)
                elif mode in {"previous", "prev", "left", "up"}:
                    target_index = current_index - 1
                elif mode in {"next", "right", "down"}:
                    target_index = current_index + 1
                elif mode == "first":
                    target_index = 0
                elif mode == "last":
                    target_index = len(pages) - 1
                else:
                    return CommandResult(False, False, "Informe mode ou target_index para reordenar a página.")
                target_index = max(0, min(len(pages) - 1, target_index))
                if target_index == current_index:
                    return CommandResult(True, False, "Página já está nessa posição.", {"page_id": page_id, "index": current_index})
                with self.session.transaction("Reordenar página"):
                    page = pages.pop(current_index)
                    pages.insert(target_index, page)
                    document.active_page_id = page_id
                return CommandResult(
                    True,
                    True,
                    "Página reordenada.",
                    {"page_id": page_id, "index": target_index, "page_ids": [item.id for item in pages]},
                )
            if name == "add_guide":
                axis = str(command.get("axis") or "x").lower(); value = float(command.get("value") or 0)
                with self.session.transaction("Adicionar guia"):
                    target = self.session.page.guides_x if axis in {"x", "v", "vertical"} else self.session.page.guides_y
                    if value not in target:
                        target.append(value); target.sort()
                return CommandResult(True, True, "Guia adicionada.")
            if name == "remove_guide":
                axis = str(command.get("axis") or "x").lower(); value = float(command.get("value") or 0); tolerance = float(command.get("tolerance") or 0.5); changed = False
                with self.session.transaction("Remover guia"):
                    target = self.session.page.guides_x if axis in {"x", "v", "vertical"} else self.session.page.guides_y
                    match = next((item for item in target if abs(item - value) <= tolerance), None)
                    if match is not None:
                        target.remove(match); changed = True
                return CommandResult(True, changed, "Guia removida." if changed else "Guia não encontrada.")
            if name == "set_snap":
                for key in ("enabled", "snap_page", "snap_objects", "snap_guides", "grid_enabled"):
                    if key in command:
                        setattr(self.snap, key, bool(command[key]))
                if "grid_spacing" in command:
                    self.snap.grid_spacing = max(0.1, float(command["grid_spacing"]))
                if "tolerance_screen_px" in command:
                    self.snap.tolerance_screen_px = max(0.1, float(command["tolerance_screen_px"]))
                return CommandResult(True, False, "Snap atualizado.", {"snap": asdict(self.snap)})
            if name == "drop_product":
                if "x" not in command or "y" not in command:
                    return CommandResult(False, False, "Drop requer coordenadas x/y do documento.")
                target = find_drop_target(
                    self.session.page,
                    float(command.get("x") or 0.0),
                    float(command.get("y") or 0.0),
                    magnet_distance=max(0.0, float(command.get("magnet_distance") or 0.0)),
                )
                if target is None:
                    return CommandResult(False, False, "Nenhum Smart Slot encontrado nesta posição.")
                bind_command: dict[str, Any] = {"name": "bind_product", "slot_id": target.slot_id}
                if isinstance(command.get("product"), dict):
                    bind_command["product"] = command["product"]
                else:
                    bind_command["product_id"] = str(command.get("product_id") or "")
                result = self.dispatch(bind_command)
                if result.ok:
                    payload = dict(result.payload or {})
                    payload["drop_target"] = target.to_dict()
                    result.payload = payload
                    result.message = "Produto aplicado ao card pelo drag-and-drop." if result.changed else result.message
                return result
            if name == "bind_product":
                slot_id = str(command.get("slot_id") or ""); product = command.get("product")
                if not isinstance(product, dict):
                    product_id = str(command.get("product_id") or ""); products = list(self.session.document.metadata.get("products") or [])
                    product = next((item for item in products if str(item.get("id") or "") == product_id), None)
                if not isinstance(product, dict):
                    return CommandResult(False, False, "Produto não encontrado.")
                slot = self.session.page.slots.get(slot_id)
                if slot is None:
                    return CommandResult(False, False, "Smart Slot não encontrado.")
                if slot.metadata.get("source") == "canva-smart-slot":
                    changed = CanvaBindingService.bind(self.session, slot_id, product)
                else:
                    self.session.bind_product(slot_id, product); changed = True
                return CommandResult(True, changed, "Produto aplicado ao Smart Slot.")
            if name in {"adjust_smart_slot", "set_smart_slot_bounds"}:
                slot_id = str(command.get("slot_id") or "")
                if slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot não encontrado.")
                required = ("x", "y", "width", "height")
                if any(key not in command for key in required):
                    return CommandResult(False, False, "Bounds x/y/width/height são obrigatórios.")
                raw_bounds = {key: float(command[key]) for key in required}
                use_snap = bool(command.get("snap", False)) and bool(self.snap.enabled)
                bounds = snap_bounds_to_grid(
                    raw_bounds,
                    spacing=float(self.snap.grid_spacing),
                    enabled=use_snap,
                    page=self.session.page,
                )
                applied = set_manual_slot_bounds(self.session, slot_id, **bounds)
                return CommandResult(True, True, "Área do Smart Slot ajustada.", {"slot_id": slot_id, "bounds": applied})
            if name == "restore_smart_slot_auto":
                slot_id = str(command.get("slot_id") or "")
                if slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot não encontrado.")
                bounds = restore_auto_slot_bounds(self.session, slot_id)
                return CommandResult(True, True, "Detecção automática do Smart Slot restaurada.", {"slot_id": slot_id, "bounds": bounds})
            if name in {"mark_smart_slot_non_product", "delete_smart_slot"}:
                slot_id = str(command.get("slot_id") or "")
                if slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot não encontrado.")
                reason = "manual-non-product" if name == "mark_smart_slot_non_product" else "manual-slot-delete"
                mark_slot_non_product(self.session, slot_id, reason=reason)
                return CommandResult(True, True, "Smart Slot removido semanticamente; conteúdo visual preservado.", {"slot_id": slot_id})
            if name == "merge_smart_slots":
                source_slot_id = str(command.get("source_slot_id") or command.get("slot_id") or "")
                target_slot_id = str(command.get("target_slot_id") or "")
                if source_slot_id not in self.session.page.slots or target_slot_id not in self.session.page.slots:
                    return CommandResult(False, False, "Smart Slot de origem/destino não encontrado.")
                merged = merge_slot_manually(self.session, source_slot_id, target_slot_id)
                return CommandResult(True, True, "Smart Slot decorativo associado ao produto.", {"source_slot_id": source_slot_id, "target_slot_id": target_slot_id, "merged_members": merged})
            if name == "undo":
                changed = self.session.undo()
                return CommandResult(True, changed, "Desfeito." if changed else "Nada para desfazer.")
            if name == "redo":
                changed = self.session.redo()
                return CommandResult(True, changed, "Refeito." if changed else "Nada para refazer.")
            return CommandResult(False, False, f"Comando desconhecido: {name}")
        except Exception as exc:
            return CommandResult(False, False, f"{type(exc).__name__}: {exc}")

    def _selection_target(self, node_id: str, scope: str) -> tuple[list[str], str]:
        page = self.session.page
        if scope in {"node", "exact", "none"}:
            return [node_id], ""
        if scope == "card":
            node = page.node(node_id)
            block_id = str(node.metadata.get("semantic_product_card_id") or "") if node is not None else ""
            members = semantic_member_ids(page, block_id) if block_id else []
            return (members or [node_id]), block_id if members else ""

        price_id = semantic_owner(page, node_id, prefer_card=False)
        price_members = semantic_member_ids(page, price_id) if price_id else []
        if price_members:
            return price_members, price_id

        card_id = semantic_owner(page, node_id, prefer_card=True)
        card = semantic_block(page, card_id) if card_id else None
        if card and bool((card.get("metadata") or {}).get("recovered")):
            card_members = semantic_member_ids(page, card_id)
            if card_members:
                return card_members, card_id

        return [node_id], ""

    def _apply_selection(
        self,
        node_ids: list[str],
        *,
        anchor_id: str,
        additive: bool,
        toggle: bool,
    ) -> None:
        valid = {node_id for node_id in node_ids if node_id in self.session.page.nodes}
        if not valid:
            return
        if toggle:
            if valid.issubset(self.session.selection):
                self.session.selection.difference_update(valid)
            else:
                self.session.selection.update(valid)
        elif additive:
            self.session.selection.update(valid)
        else:
            self.session.selection = set(valid)
        self.session.anchor_id = anchor_id if anchor_id in self.session.selection else next(iter(self.session.selection), None)

    def _copy_selection(self) -> int:
        roots = list(self.session._selection_roots(editable_only=False))
        if not roots:
            return 0
        page = self.session.page
        nodes: dict[str, GraphicsNode] = {}
        for root in roots:
            for node_id in self.session._tree_ids(root.id):
                node = page.node(node_id)
                if node is not None:
                    nodes[node_id] = copy.deepcopy(node)
        source_blocks_raw = page.metadata.get("semantic_blocks")
        self._clipboard = {
            "root_ids": [root.id for root in roots],
            "nodes": nodes,
            "slots": copy.deepcopy(list(page.slots.values())),
            "blocks": copy.deepcopy(source_blocks_raw) if isinstance(source_blocks_raw, dict) else {},
        }
        return len(nodes)

    def _paste_clipboard(self, dx: float, dy: float) -> tuple[list[str], list[str]]:
        clipboard = self._clipboard
        if not clipboard:
            return [], []
        source_nodes = dict(clipboard.get("nodes") or {})
        root_ids = [str(node_id) for node_id in clipboard.get("root_ids") or []]
        if not source_nodes or not root_ids:
            return [], []
        mapping: dict[str, str] = {}
        created: list[str] = []
        slot_ids: list[str] = []
        source_slots = copy.deepcopy(list(clipboard.get("slots") or []))
        source_blocks = copy.deepcopy(dict(clipboard.get("blocks") or {}))

        with self.session.transaction("Colar elementos"):
            for root_id in root_ids:
                if root_id not in source_nodes:
                    continue
                created.append(self._paste_tree_snapshot(root_id, None, dx, dy, mapping, source_nodes))
            slot_ids = self._duplicate_semantic_state(mapping, source_slots, source_blocks)

        self.session.selection = set(created)
        self.session.anchor_id = created[-1] if created else None
        return created, slot_ids

    def _paste_tree_snapshot(
        self,
        node_id: str,
        new_parent_id: str | None,
        dx: float,
        dy: float,
        mapping: dict[str, str],
        source_nodes: dict[str, GraphicsNode],
    ) -> str:
        source = source_nodes[node_id]
        clone = source.clone()
        clone.transform.x += float(dx)
        clone.transform.y += float(dy)
        clone.z_index += 1
        mapping[node_id] = clone.id
        self.session.page.add_node(clone, parent_id=new_parent_id)
        for child_id in source.children:
            if child_id in source_nodes:
                self._paste_tree_snapshot(child_id, clone.id, dx, dy, mapping, source_nodes)
        return clone.id

    def _duplicate_selected_with_semantics(self, dx: float, dy: float) -> tuple[list[str], list[str]]:
        roots = list(self.session._selection_roots(editable_only=False))
        if not roots:
            return [], []
        page = self.session.page
        source_slots = copy.deepcopy(list(page.slots.values()))
        source_blocks_raw = page.metadata.get("semantic_blocks")
        source_blocks = copy.deepcopy(source_blocks_raw) if isinstance(source_blocks_raw, dict) else {}
        created: list[str] = []
        mapping: dict[str, str] = {}
        slot_ids: list[str] = []

        with self.session.transaction("Duplicar elementos"):
            for node in roots:
                tree_mapping: dict[str, str] = {}
                self.session._duplicate_tree(node.id, node.parent_id, float(dx), float(dy), tree_mapping)
                mapping.update(tree_mapping)
                created.append(tree_mapping[node.id])
            slot_ids = self._duplicate_semantic_state(mapping, source_slots, source_blocks)

        self.session.selection = set(created)
        self.session.anchor_id = created[-1] if created else None
        return created, slot_ids

    def _duplicate_semantic_state(
        self,
        mapping: dict[str, str],
        source_slots: list[Any],
        source_blocks: dict[str, Any],
    ) -> list[str]:
        if not mapping:
            return []
        page = self.session.page

        for clone_id in mapping.values():
            node = page.node(clone_id)
            if node is None:
                continue
            node.metadata.pop("semantic_price_block_id", None)
            node.metadata.pop("semantic_price_role", None)
            node.metadata.pop("semantic_product_card_id", None)
            node.metadata.pop("semantic_recovered_editable", None)
            node.metadata.pop("semantic_source_locked", None)
            node.style.pop("semantic_price_block_id", None)
            node.style.pop("semantic_price_role", None)

        page_blocks_raw = page.metadata.get("semantic_blocks")
        if not isinstance(page_blocks_raw, dict):
            page_blocks_raw = {}
            page.metadata["semantic_blocks"] = page_blocks_raw
        created_slots: list[str] = []

        for source_slot in source_slots:
            bound_ids = {str(node_id) for node_id in source_slot.node_by_role.values() if str(node_id)}
            extras = source_slot.metadata.get("extra_bindings")
            if isinstance(extras, dict):
                for node_ids in extras.values():
                    if isinstance(node_ids, (list, tuple, set)):
                        bound_ids.update(str(node_id) for node_id in node_ids if str(node_id))
                    elif node_ids:
                        bound_ids.add(str(node_ids))
            if not bound_ids or not bound_ids.issubset(mapping):
                continue

            new_slot = copy.deepcopy(source_slot)
            new_slot.id = _id("slot")
            new_slot.page_id = page.id
            new_slot.node_by_role = {
                str(role): mapping[str(node_id)]
                for role, node_id in source_slot.node_by_role.items()
                if str(node_id) in mapping
            }
            new_slot.metadata = copy.deepcopy(source_slot.metadata)
            new_slot.metadata["semantic_recovered"] = False
            new_slot.metadata["duplicated_from_slot_id"] = source_slot.id
            new_slot.metadata.pop("semantic_product_card_id", None)
            new_slot.metadata.pop("semantic_price_block_ids", None)
            source_group_id = str(new_slot.metadata.get("source_group_id") or "")
            if source_group_id in mapping:
                new_slot.metadata["source_group_id"] = mapping[source_group_id]
            extra_bindings = new_slot.metadata.get("extra_bindings")
            if isinstance(extra_bindings, dict):
                remapped_extras: dict[str, Any] = {}
                for role, node_ids in extra_bindings.items():
                    if isinstance(node_ids, (list, tuple, set)):
                        remapped_extras[str(role)] = [mapping[str(node_id)] for node_id in node_ids if str(node_id) in mapping]
                    elif str(node_ids) in mapping:
                        remapped_extras[str(role)] = mapping[str(node_ids)]
                new_slot.metadata["extra_bindings"] = remapped_extras
            page.slots[new_slot.id] = new_slot

            source_slot_blocks = [
                (str(block_id), block)
                for block_id, block in source_blocks.items()
                if isinstance(block, dict) and str(block.get("slot_id") or "") == source_slot.id
            ]
            block_id_map: dict[str, str] = {}
            price_index = 0
            for old_block_id, block in source_slot_blocks:
                kind = str(block.get("kind") or "")
                if kind == "product_card":
                    new_block_id = f"productcard:{new_slot.id}"
                elif kind == "price_block":
                    price_index += 1
                    suffix = "app-price" if "app-price" in old_block_id else "price" if price_index == 1 else f"price-{price_index}"
                    new_block_id = f"priceblock:{new_slot.id}:{suffix}"
                else:
                    new_block_id = _id("semantic")
                block_id_map[old_block_id] = new_block_id

            new_price_ids: list[str] = []
            new_product_id = ""
            for old_block_id, source_block in source_slot_blocks:
                new_block = copy.deepcopy(source_block)
                new_block_id = block_id_map[old_block_id]
                kind = str(new_block.get("kind") or "")
                new_block["id"] = new_block_id
                new_block["slot_id"] = new_slot.id
                new_block["members"] = [mapping[str(node_id)] for node_id in source_block.get("members") or [] if str(node_id) in mapping]
                roles: dict[str, list[str]] = {}
                for role, node_ids in dict(source_block.get("roles") or {}).items():
                    roles[str(role)] = [mapping[str(node_id)] for node_id in node_ids if str(node_id) in mapping]
                new_block["roles"] = roles
                geometry = dict(source_block.get("template_geometry") or {})
                new_block["template_geometry"] = {
                    mapping[str(node_id)]: copy.deepcopy(value)
                    for node_id, value in geometry.items()
                    if str(node_id) in mapping
                }
                bounds = page.bounds(new_block["members"])
                if bounds is not None:
                    new_block["bounds"] = {
                        "x": bounds.x,
                        "y": bounds.y,
                        "width": bounds.width,
                        "height": bounds.height,
                    }
                metadata = copy.deepcopy(source_block.get("metadata") or {})
                for key in ("source_group_id", "name_node_id", "image_node_id"):
                    node_id = str(metadata.get(key) or "")
                    if node_id in mapping:
                        metadata[key] = mapping[node_id]
                content_members = metadata.get("content_members")
                if isinstance(content_members, list):
                    metadata["content_members"] = [mapping[str(node_id)] for node_id in content_members if str(node_id) in mapping]
                price_blocks = metadata.get("price_blocks")
                if isinstance(price_blocks, list):
                    metadata["price_blocks"] = [block_id_map.get(str(block_id), str(block_id)) for block_id in price_blocks]
                metadata["smart_slot_id"] = new_slot.id
                metadata["duplicated_from_block_id"] = old_block_id
                if "stable_key" in metadata:
                    metadata["stable_key"] = new_slot.id
                new_block["metadata"] = metadata
                page_blocks_raw[new_block_id] = new_block

                if kind == "price_block":
                    new_price_ids.append(new_block_id)
                    for role, node_ids in roles.items():
                        for node_id in node_ids:
                            node = page.node(node_id)
                            if node is None:
                                continue
                            node.metadata["semantic_price_block_id"] = new_block_id
                            node.metadata["semantic_price_role"] = role
                            if node.kind is NodeKind.TEXT:
                                node.style["semantic_price_block_id"] = new_block_id
                                node.style["semantic_price_role"] = role
                elif kind == "product_card":
                    new_product_id = new_block_id
                    semantic_members = set(new_block.get("members") or [])
                    semantic_members.update(metadata.get("content_members") or [])
                    for node_ids in roles.values():
                        semantic_members.update(node_ids)
                    for node_id in semantic_members:
                        node = page.node(str(node_id))
                        if node is not None:
                            node.metadata["semantic_product_card_id"] = new_block_id

            if new_product_id:
                new_slot.metadata["semantic_product_card_id"] = new_product_id
            new_slot.metadata["semantic_price_block_ids"] = new_price_ids
            created_slots.append(new_slot.id)

        return created_slots

    def _resize_handle(self, command: dict[str, Any]) -> CommandResult:
        node_id = str(command.get("node_id") or self.session.anchor_id or ""); node = self.session.page.node(node_id)
        if node is None or node.locked:
            return CommandResult(False, False, "Elemento não editável.")
        handle = str(command.get("handle") or "se").lower(); dx = float(command.get("dx") or 0); dy = float(command.get("dy") or 0); keep_ratio = bool(command.get("keep_ratio", False)); min_size = max(1.0, float(command.get("min_size") or 4.0))
        t = node.transform; x, y, w, h = t.x, t.y, t.width, t.height; right, bottom = x + w, y + h; nx, ny, nr, nb = x, y, right, bottom
        if "w" in handle: nx = min(right - min_size, x + dx)
        if "e" in handle: nr = max(x + min_size, right + dx)
        if "n" in handle: ny = min(bottom - min_size, y + dy)
        if "s" in handle: nb = max(y + min_size, bottom + dy)
        nw, nh = nr - nx, nb - ny
        if keep_ratio and w > 0 and h > 0:
            ratio = w / h
            if ("e" in handle or "w" in handle) and not ("n" in handle or "s" in handle): nh = nw / ratio; nb = ny + nh
            elif ("n" in handle or "s" in handle) and not ("e" in handle or "w" in handle): nw = nh * ratio; nr = nx + nw
            else:
                if abs(nw - w) / max(w, 1) >= abs(nh - h) / max(h, 1): nh = nw / ratio
                else: nw = nh * ratio
                if "w" in handle: nx = right - nw
                else: nr = x + nw
                if "n" in handle: ny = bottom - nh
                else: nb = y + nh
        self.session.resize_node(node_id, x=nx, y=ny, width=max(min_size, nw), height=max(min_size, nh), min_size=min_size)
        return CommandResult(True, True, "Elemento redimensionado.")


def _optional_float(data: dict[str, Any], key: str) -> float | None:
    if key not in data or data[key] is None or data[key] == "": return None
    return float(data[key])


def _optional_bool(data: dict[str, Any], key: str) -> bool | None:
    if key not in data or data[key] is None: return None
    return bool(data[key])