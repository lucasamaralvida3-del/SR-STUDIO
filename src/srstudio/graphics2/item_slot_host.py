from __future__ import annotations

"""Graphics2 host adapter for explicit, manual ItemSlot authoring.

The certified Qt host remains the implementation of autosave, file IO, GPU
selection and QML lifetime.  This module only swaps the command router factory
used by that host, adding manual ItemSlot commands and payload data.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
import json
import os

from . import package as _package
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
from .slot_corpus_bindings import bind_product_to_quinta3_slot
from .slot_corpus_calibration import QUINTA3_SUPERVISED_PROFILES
from .slot_corpus_families import QUINTA3_FAMILY_PRESETS, install_quinta3_family_presets
from .slot_corpus_full_card import MEAT_FAMILY_ID
from .slot_corpus_meat_strip_ownership import next_meat_profile, normalize_meat_strip_ownership
from .slot_corpus_variant_runtime import apply_quinta3_variant, create_quinta3_item_slot


# One certified source example is used only to materialize the initial visual
# variant when the user creates a family from the Studio menu.  Applying a
# product tagged with another supervised profile can switch parameters inside
# the same base family; it never creates another preset/family.
_QUINTA3_DEFAULT_PROFILE_BY_FAMILY = {
    "quinta3-meat-strip": "costela",
    "quinta3-wood-plaque": "bolacha",
    "quinta3-compact-promo": "odor-boom",
    "quinta3-club-side": "amaciante",
    "quinta3-stationery-round": "cadernos",
}


class ItemSlotCommandRouter(GraphicsCommandRouter):
    """Adds manual authoring commands without changing automatic detection."""

    def payload(self) -> dict[str, Any]:
        # The five certified Quinta3 families live in the existing custom
        # preset store. Installing them here makes the generic QML preset menu
        # see them in every real Studio session without a UI-specific fork.
        install_quinta3_family_presets(self.session.document)
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
            if preset_id in QUINTA3_FAMILY_PRESETS:
                profile_id = (
                    next_meat_profile(self.session.page)
                    if preset_id == MEAT_FAMILY_ID
                    else _QUINTA3_DEFAULT_PROFILE_BY_FAMILY[preset_id]
                )
                profile = QUINTA3_SUPERVISED_PROFILES[profile_id]
                slot = create_quinta3_item_slot(
                    self.session,
                    preset_id,
                    variant=str(profile["variant"]),
                    parameters={"supervisedProfile": profile_id},
                    x=_optional_number(command.get("x")),
                    y=_optional_number(command.get("y")),
                )
                if preset_id == MEAT_FAMILY_ID:
                    with self.session.transaction("Normalizar ownership Meat Strip"):
                        normalize_meat_strip_ownership(self.session.page, slot, profile_id=profile_id)
            else:
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

                if slot.metadata.get("quinta3_family"):
                    profile_id = str(product.get("quinta3_supervised_profile") or "").strip()
                    profile = QUINTA3_SUPERVISED_PROFILES.get(profile_id)
                    if profile and str(profile.get("family_id") or "") == str(slot.metadata.get("preset_id") or ""):
                        apply_quinta3_variant(
                            self.session,
                            slot.id,
                            variant=str(profile["variant"]),
                            parameters={"supervisedProfile": profile_id},
                        )
                    if str(slot.metadata.get("preset_id") or "") == MEAT_FAMILY_ID:
                        effective_profile = profile_id or str(slot.metadata.get("full_card_profile") or slot.metadata.get("supervised_profile") or "costela")
                        with self.session.transaction("Normalizar ownership Meat Strip"):
                            normalize_meat_strip_ownership(self.session.page, slot, profile_id=effective_profile)
                    changed = bind_product_to_quinta3_slot(self.session, slot_id, product)
                else:
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


def _bridge_save_wrapper(
    save_fn: Callable[..., Path],
    canonical_source: Path | None,
) -> Callable[..., Path]:
    """Mirror explicit Save-As into the Full Studio canonical bridge session.

    The Full Studio launcher always reopens its project-scoped bridge package.
    Historically the G2 Save button wrote only the path selected in the dialog,
    then switched ``context.source`` to that copy.  Relaunching from Full Studio
    therefore reopened the untouched bridge package and could show 0 ItemSlots.
    Keep the user-selected copy, but make the authoritative bridge package carry
    the exact same serialized scene before the app can be reopened.
    """

    canonical = canonical_source.resolve() if canonical_source is not None else None

    def save(document, path, *, embed_local_assets: bool = True):
        written = save_fn(document, path, embed_local_assets=embed_local_assets)
        if canonical is not None:
            try:
                target = Path(written).resolve()
            except OSError:
                target = Path(written).absolute()
            if target != canonical:
                save_fn(document, canonical, embed_local_assets=embed_local_assets)
        return written

    return save


def _canonical_bridge_source(kwargs: dict[str, Any]) -> Path | None:
    if str(os.environ.get("SR_GRAPHICS_ENGINE_2_BRIDGE") or "").strip() != "1":
        return None
    context = kwargs.get("launch_context")
    source = getattr(context, "source", None)
    if source is None:
        return None
    path = Path(source)
    return path if path.suffix.lower() == ".srscene" else None


def launch_qt_quick_editor(*args, **kwargs):
    previous_router = _base.GraphicsCommandRouter
    previous_save = _package.save_package
    _base.GraphicsCommandRouter = ItemSlotCommandRouter
    canonical = _canonical_bridge_source(kwargs)
    if canonical is not None:
        # qt_host imports save_package dynamically inside saveSceneAs, so this
        # scoped replacement affects explicit project saves only while the Qt
        # host event loop is alive. Autosave keeps its own imported reference.
        _package.save_package = _bridge_save_wrapper(previous_save, canonical)
    try:
        return _base.launch_qt_quick_editor(*args, **kwargs)
    finally:
        _package.save_package = previous_save
        _base.GraphicsCommandRouter = previous_router


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
