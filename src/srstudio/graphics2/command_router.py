from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import json

from .drop_target import find_drop_target
from .geometry import SnapEngine, SnapSettings
from .import_bridge import CanvaBindingService
from .model import GraphicsNode, NodeKind, Transform
from .operations import GraphicsSession
from .semantic_blocks import semantic_block, semantic_member_ids, semantic_owner


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
        self.snap = SnapSettings()

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
            "snap": asdict(self.snap),
            "products": list(self.session.document.metadata.get("products") or []),
        }
        return scene

    def dispatch_json(self, raw: str) -> str:
        try:
            command = json.loads(raw)
            if not isinstance(command, dict):
                raise ValueError("Comando JSON deve ser um objeto.")
            result = self.dispatch(command)
        except Exception as exc:
            result = CommandResult(False, False, f"Erro: {exc}")
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
                created = self.session.duplicate_selected(float(command.get("dx") or 20.0), float(command.get("dy") or 20.0))
                return CommandResult(True, bool(created), "Elementos duplicados." if created else "Nada para duplicar.", {"node_ids": created})
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
                self.session.set_image_crop(node_id, fit=str(command["fit"]) if "fit" in command else None, focus_x=_optional_float(command, "focus_x"), focus_y=_optional_float(command, "focus_y"), zoom=_optional_float(command, "zoom"), flip_x=_optional_bool(command, "flip_x"), flip_y=_optional_bool(command, "flip_y"))
                return CommandResult(True, bool(node_id), "Imagem ajustada.")
            if name in {"add_page", "duplicate_page"}:
                page_id = self.session.add_page(name=str(command.get("name_value") or "") or None, duplicate_active=name == "duplicate_page")
                return CommandResult(True, True, "Página criada.", {"page_id": page_id})
            if name == "select_page":
                page_id = str(command.get("page_id") or "")
                if self.session.document.page(page_id) is None:
                    return CommandResult(False, False, "Página inexistente.")
                self.session.document.active_page_id = page_id; self.session.clear_selection()
                return CommandResult(True, False, "Página selecionada.")
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

        # Auto sempre prioriza PriceBlock. Assim um clique no preço mantém
        # R$ + reais + centavos + KG/UN atômicos, sem transformar todos os
        # ProductCards normais em objetos indivisíveis.
        price_id = semantic_owner(page, node_id, prefer_card=False)
        price_members = semantic_member_ids(page, price_id) if price_id else []
        if price_members:
            return price_members, price_id

        # ProductCards recuperados de grupos PPTX são diferentes: o próprio
        # arquivo fonte já declarou que nome/imagem/backplate/preço pertencem ao
        # mesmo grupo. Neles, clicar no nome ou imagem seleciona automaticamente
        # o grupo real, evitando que a edição volte a desmontar o layout Canva.
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
