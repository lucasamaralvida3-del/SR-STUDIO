from __future__ import annotations

"""Graphics2 host adapter for explicit, manual ItemSlot authoring.

The certified Qt host remains the implementation of autosave, file IO, GPU
selection and QML lifetime.  This module only swaps the command router factory
used by that host, adding manual ItemSlot commands and payload data.
"""

from dataclasses import asdict
from typing import Any
import json

from . import qt_host as _base
from .command_router import CommandResult, GraphicsCommandRouter
from .item_slots import (
    bind_product_to_item_slot,
    create_item_slot,
    duplicate_item_slot,
    is_manual_item_slot,
    item_slot_for_node,
    list_item_slot_presets,
    list_item_slots,
    refresh_all_item_slots,
    save_item_slot_as_preset,
    set_item_slot_role_bounds,
)


class ItemSlotCommandRouter(GraphicsCommandRouter):
    """Adds manual authoring commands without changing automatic detection."""

    def payload(self) -> dict[str, Any]:
        refresh_all_item_slots(self.session.document)
        payload = super().payload()
        editor = payload.setdefault("editor", {})
        editor["item_slot_presets"] = list_item_slot_presets(self.session.document)
        editor["item_slots"] = list_item_slots(self.session.document)
        return payload

    def dispatch_json(self, raw: str, *, include_scene_payload: bool = True) -> str:
        try:
            command = json.loads(raw)
            if not isinstance(command, dict):
                raise ValueError("Comando JSON deve ser um objeto.")
            result = self.dispatch(command)
        except Exception as exc:
            result = CommandResult(False, False, f"Erro: {exc}")
        if include_scene_payload:
            result.payload = self.payload()
        return json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def dispatch(self, command: dict[str, Any]) -> CommandResult:
        name = str(command.get("name") or "").strip().lower()
        if name == "add_item_slot":
            preset_id = str(command.get("preset_id") or "simples")
            slot = create_item_slot(
                self.session,
                preset_id,
                x=_optional_number(command.get("x")),
                y=_optional_number(command.get("y")),
            )
            return CommandResult(
                True,
                True,
                f"Slot de Item adicionado · {slot.name}",
                {"slot_id": slot.id, "root_node_id": slot.metadata.get("root_node_id", ""), "preset_id": preset_id},
            )

        if name == "select_item_slot":
            slot = self.session.page.slots.get(str(command.get("slot_id") or ""))
            if not is_manual_item_slot(slot):
                return CommandResult(False, False, "ItemSlot não encontrado.")
            root_id = str(slot.metadata.get("root_node_id") or "")
            if self.session.page.node(root_id) is None:
                return CommandResult(False, False, "Raiz do ItemSlot não encontrada.")
            self.session.selection = {root_id}
            self.session.anchor_id = root_id
            return CommandResult(True, False, "ItemSlot selecionado.", {"slot_id": slot.id, "root_node_id": root_id})

        if name == "set_item_slot_role_bounds":
            changed = set_item_slot_role_bounds(
                self.session,
                str(command.get("slot_id") or ""),
                str(command.get("role") or ""),
                x=float(command.get("x") or 0.0),
                y=float(command.get("y") or 0.0),
                width=float(command.get("width") or 1.0),
                height=float(command.get("height") or 1.0),
            )
            return CommandResult(True, changed, "Área interna atualizada." if changed else "Área interna não encontrada.")

        if name == "duplicate_item_slot":
            slot_id = str(command.get("slot_id") or "")
            clone = duplicate_item_slot(
                self.session,
                slot_id,
                dx=float(command.get("dx") or 20.0),
                dy=float(command.get("dy") or 20.0),
                include_product=bool(command.get("include_product", False)),
            )
            return CommandResult(
                True,
                True,
                "Slot duplicado · estrutura vazia preservada." if not command.get("include_product") else "Slot duplicado com produto.",
                {"slot_id": clone.id, "root_node_id": clone.metadata.get("root_node_id", "")},
            )

        if name == "save_item_slot_preset":
            preset = save_item_slot_as_preset(
                self.session,
                str(command.get("slot_id") or ""),
                str(command.get("preset_name") or ""),
            )
            return CommandResult(True, True, f"Modelo de slot salvo · {preset['name']}", {"preset": preset})

        if name == "duplicate":
            manual = item_slot_for_node(self.session.page, self.session.anchor_id or "")
            if manual is not None:
                clone = duplicate_item_slot(
                    self.session,
                    manual.id,
                    dx=float(command.get("dx") or 20.0),
                    dy=float(command.get("dy") or 20.0),
                    include_product=bool(command.get("include_product", False)),
                )
                return CommandResult(
                    True,
                    True,
                    "ItemSlot duplicado · produto não copiado." if not command.get("include_product") else "ItemSlot duplicado com produto.",
                    {"slot_id": clone.id, "root_node_id": clone.metadata.get("root_node_id", "")},
                )

        if name == "bind_product":
            slot_id = str(command.get("slot_id") or "")
            slot = self.session.page.slots.get(slot_id)
            if is_manual_item_slot(slot):
                product = command.get("product")
                if not isinstance(product, dict):
                    product_id = str(command.get("product_id") or "")
                    products = list(self.session.document.metadata.get("products") or [])
                    product = next((item for item in products if str(item.get("id") or "") == product_id), None)
                if not isinstance(product, dict):
                    return CommandResult(False, False, "Produto não encontrado.")
                changed = bind_product_to_item_slot(self.session, slot_id, product)
                return CommandResult(True, changed, "Produto aplicado ao ItemSlot.")

        result = super().dispatch(command)
        if result.changed and name in {"drop_product", "paste", "undo", "redo", "delete"}:
            refresh_all_item_slots(self.session.document)
        return result


def _optional_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def launch_qt_quick_editor(*args, **kwargs):
    previous = _base.GraphicsCommandRouter
    _base.GraphicsCommandRouter = ItemSlotCommandRouter
    try:
        return _base.launch_qt_quick_editor(*args, **kwargs)
    finally:
        _base.GraphicsCommandRouter = previous


# Keep the certified host API surface.  entrypoint.py imports this module under
# the name ``qt_host`` so all CLI/probe/load behavior remains unchanged.
build_parser = _base.build_parser
load_launch_context = _base.load_launch_context
build_editor_diagnostics = _base.build_editor_diagnostics
prepare_qml_payload = _base.prepare_qml_payload
probe_graphics_api = _base.probe_graphics_api
GraphicsLaunchContext = _base.GraphicsLaunchContext
GraphicsApiProbe = _base.GraphicsApiProbe
qt_quick_available = _base.qt_quick_available
main = _base.main
