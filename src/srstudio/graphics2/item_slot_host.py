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
from .slot_limpeza_blue import (
    PRESET_ID as LIMPEZA_BLUE_ID,
    bind_product_to_limpeza_blue_slot,
    create_limpeza_blue_slot,
    inspect_limpeza_blue_slot,
)
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
        # Creating five Quinta3 families during every scene serialization
        # was wasteful and revived models removed from the creation UI.
        # Migrate older Limpeza slots once, not for every repaint or selection.
        if not getattr(self, "_limpeza_migrated", False):
            # Preserve certified historical families for existing documents
            # and API clients; the new Qt picker displays only Beta44 styles.
            install_quinta3_family_presets(self.session.document)
            refresh_all_item_slots(self.session.document)
            self._limpeza_migrated = True
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
        if name == "adjust_smart_slot":
            # The certified Azul implementation remains handled by the base
            # command router. New manual slots need native group transform.
            from .model import Rect
            slot = self.session.page.slots.get(str(command.get("slot_id") or ""))
            if is_manual_item_slot(slot) and slot.metadata.get("preset_id") in (
                    "individual-beta44", "multi-cell-beta44"):
                root_id = str(slot.metadata.get("root_node_id") or "")
                root = self.session.page.node(root_id)
                if root is None:
                    return CommandResult(False, False, "Raiz do slot não encontrada.")
                try:
                    target = Rect(float(command["x"]), float(command["y"]),
                                  max(1.0, float(command["width"])),
                                  max(1.0, float(command["height"])))
                except (ValueError, TypeError, KeyError):
                    return CommandResult(False, False, "Dimensões inválidas.")
                self.session.resize_node(root_id, x=target.x, y=target.y,
                                         width=target.width, height=target.height)
                return CommandResult(True, True, "Smart Slot reposicionado.", {"slot_id": slot.id})

        if name == "add_multi_item_slot":
            from .multi_item_strip import create_multi_item_strip
            try:
                result = create_multi_item_strip(
                    self.session,
                    count=int(command.get("count", 6)),
                    price_mode=str(command.get("price_mode") or "auto"),
                    x=_optional_number(command.get("x")),
                    y=_optional_number(command.get("y")),
                )
            except (ValueError, TypeError) as exc:
                return CommandResult(False, False, str(exc))
            return CommandResult(True, True, "Faixa Multi Itens inserida.", result)

        if name == "set_item_price_mode":
            from .model import BindingRole
            mode = str(command.get("mode") or "auto")
            if mode not in ("auto", "one", "two"):
                return CommandResult(False, False, "Modo inválido.")
            root_id = str(command.get("multi_root_id") or "")
            selected = [str(command.get("slot_id") or "")]
            if root_id:
                root = self.session.page.node(root_id)
                if root is None or not root.metadata.get("multi_slot_beta44"):
                    return CommandResult(False, False, "Faixa Multi não encontrada.")
                selected = list(root.metadata.get("child_slot_ids") or [])
            updated = []
            for sid in selected:
                slot = self.session.page.slots.get(sid)
                if not is_manual_item_slot(slot):
                    continue
                if slot.metadata.get("preset_id") not in ("individual-beta44", "multi-cell-beta44"):
                    continue
                with self.session.transaction("Alterar quantidade de preços"):
                    slot.metadata["price_mode"] = mode
                    second = self.session.page.node(str(slot.node_by_role.get(BindingRole.RETAIL_PRICE.value) or ""))
                    if second is not None:
                        second.visible = mode == "two" or (mode == "auto" and slot.metadata.get("price_variant") == "two")
                        slot.metadata["price_variant"] = "two" if second.visible else "one"
                updated.append(sid)
            return CommandResult(bool(updated), bool(updated), "Modo de preços atualizado.", {"slot_ids": updated})

        if name == "add_item_slot":
            preset_id = str(command.get("preset_id") or LIMPEZA_BLUE_ID)
            if preset_id not in (LIMPEZA_BLUE_ID, "individual-beta44", "multi-cell-beta44", *QUINTA3_FAMILY_PRESETS):
                return CommandResult(False, False, "Modelo de criação indisponível.")
            if preset_id == LIMPEZA_BLUE_ID:
                slot = create_limpeza_blue_slot(
                    self.session,
                    x=_optional_number(command.get("x")),
                    y=_optional_number(command.get("y")),
                )
            elif preset_id in QUINTA3_FAMILY_PRESETS:
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

        if name == "apply_promotion_layout":
            from .promotion_layouts import plan_promotion
            from .model import Transform
            try:
                plan = plan_promotion(
                    str(command.get("mode") or "auto"),
                    count=command.get("count"),
                    logo_reserved=float(command.get("logo_reserved", 0.24)),
                    variation=int(command.get("variation", 0)),
                )
            except (ValueError, AssertionError, TypeError) as exc:
                return CommandResult(False, False, str(exc))
            price_mode = str(command.get("price_mode") or "auto")
            if price_mode not in ("auto", "one", "two"):
                return CommandResult(False, False, "Modo de preços inválido.")
            # Multiple template insertions must not obscure existing
            # product cards. Preserve the old page and create a fresh page
            # with the same dimensions when any Smart Slots already exist.
            if self.session.page.slots:
                previous = self.session.page
                previous_width, previous_height = previous.width, previous.height
                previous_background = previous.background
                self.session.add_page(name="Layout promocional")
                with self.session.transaction("Preservar formato da página"):
                    self.session.page.width = previous_width
                    self.session.page.height = previous_height
                    self.session.page.background = previous_background
            page = self.session.page
            created = []
            # Each template is inserted as editable Smart Slots.
            for position in plan.placements:
                if plan.mode == "eleven" and position.index in (7, 8, 9, 10):
                    # These four items are already owned by the 5-item group.
                    continue
                if plan.mode == "eleven" and position.index == 6:
                    from .multi_item_strip import create_multi_item_strip
                    end = plan.placements[10]
                    x = page.width * position.x
                    y = page.height * position.y
                    group_width = page.width * (end.x + end.width - position.x)
                    group_height = page.height * position.height
                    multi = create_multi_item_strip(self.session, count=5,
                                                    price_mode=price_mode,
                                                    x=x, y=y)
                    self.session.resize_node(
                        multi["root_node_id"], x=x, y=y,
                        width=group_width, height=group_height)
                    created.extend(multi["slot_ids"])
                    continue
                target_x = page.width * position.x
                target_y = page.height * position.y
                target_w = page.width * position.width
                target_h = page.height * position.height
                slot = create_item_slot(self.session, "individual-beta44",
                                        x=target_x, y=target_y)
                slot.metadata["price_mode"] = price_mode
                root_id = str(slot.metadata.get("root_node_id") or "")
                root = page.node(root_id)
                original = root.transform
                sx = target_w / max(1.0, original.width)
                sy = target_h / max(1.0, original.height)
                with self.session.transaction("Dimensionar slot promocional"):
                    for node_id in [root_id] + list(page.descendants(root_id)):
                        node = page.node(node_id)
                        if node is None:
                            continue
                        t = node.transform
                        node.transform = Transform(
                            x=target_x + (t.x - original.x) * sx,
                            y=target_y + (t.y - original.y) * sy,
                            width=max(1.0, t.width * sx),
                            height=max(1.0, t.height * sy),
                        )
                created.append(slot.id)
            return CommandResult(True, True, "Layout promocional inserido.", {
                "slot_ids": created, "logo_reserved": plan.logo_reserved,
                "page_id": page.id
            })

        if name == "plan_promotion_layout":
            from .promotion_layouts import plan_promotion
            try:
                plan = plan_promotion(
                    str(command.get("mode") or "auto"),
                    count=command.get("count"),
                    logo_reserved=float(command.get("logo_reserved", 0.24)),
                    variation=int(command.get("variation", 0)),
                )
            except (ValueError, AssertionError, TypeError) as exc:
                return CommandResult(False, False, str(exc))
            return CommandResult(True, False, "Composição calculada.", {
                "logo_reserved": plan.logo_reserved,
                "placements": [item.as_dict() for item in plan.placements],
            })

        if name == "inspect_limpeza_blue_slot":
            slot = self.session.page.slots.get(str(command.get("slot_id") or ""))
            if slot is None:
                return CommandResult(False, False, "Slot inexistente.")
            report = inspect_limpeza_blue_slot(self.session.page, slot)
            return CommandResult(True, False, "Inspeção do perfil Limpeza Azul.", report)

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

                if slot.metadata.get("limpeza_blue_profile") == LIMPEZA_BLUE_ID:
                    changed = bind_product_to_limpeza_blue_slot(self.session, slot_id, product)
                elif slot.metadata.get("quinta3_family"):
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
