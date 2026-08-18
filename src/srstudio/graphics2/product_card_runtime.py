from __future__ import annotations

"""High-level ProductCard creation and command contract for Graphics2.

Imported templates already expose SmartSlots. Daily production also needs a
small, deterministic way to create a new intelligent card without requiring the
QML layer to know individual node/binding details. This module adds that
semantic operation while leaving rendering and editor UI ownership untouched.
"""

from dataclasses import asdict, dataclass
from typing import Any

from .model import GraphicsNode, NodeKind, SmartSlot, Transform


@dataclass(slots=True)
class ProductCardCreation:
    slot_id: str
    product_card_id: str
    node_by_role: dict[str, str]
    extra_bindings: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def install_product_card_runtime(session_type: Any, semantic_module: Any) -> None:
    if bool(getattr(session_type, "_sr_product_card_runtime_installed", False)):
        return

    def create_product_card(
        self: Any,
        *,
        x: float = 80.0,
        y: float = 80.0,
        width: float = 420.0,
        height: float = 360.0,
        name: str = "Novo produto",
        include_image: bool = True,
        include_description: bool = True,
        include_quantity: bool = True,
        include_validity: bool = False,
        include_app_price: bool = False,
        include_wholesale: bool = False,
    ) -> ProductCardCreation:
        width = max(260.0, float(width))
        height = max(260.0, float(height))
        x = float(x)
        y = float(y)
        page = self.page

        primary: dict[str, str] = {}
        extra: dict[str, list[str]] = {}

        def add_text(
            key: str,
            role: str,
            text: str,
            rx: float,
            ry: float,
            rw: float,
            rh: float,
            *,
            font_size: float,
            visible: bool = True,
        ) -> GraphicsNode:
            node = GraphicsNode(
                kind=NodeKind.TEXT,
                name=f"G2_{key.upper()}",
                text=text,
                visible=visible,
                transform=Transform(
                    x=x + width * rx,
                    y=y + height * ry,
                    width=max(24.0, width * rw),
                    height=max(18.0, height * rh),
                ),
                style={
                    "font_size": font_size,
                    "font_weight": 700
                    if role in {"name", "price_complete", "app_price_complete", "wholesale_price"}
                    else 400,
                    "align": "center"
                    if "price" in role or role in {"currency", "price_currency", "unit", "quantity"}
                    else "left",
                },
                metadata={
                    "source": "g2-product-card",
                    "binding_template_text": text,
                    "product_card_role": role,
                },
            )
            page.add_node(node)
            return node

        with self.transaction("Criar ProductCard"):
            name_node = add_text(
                "product_name", "name", name, 0.04, 0.04, 0.92, 0.14, font_size=26.0
            )
            primary["name"] = name_node.id

            if include_description:
                description = add_text(
                    "description",
                    "description",
                    "",
                    0.05,
                    0.18,
                    0.90,
                    0.09,
                    font_size=14.0,
                    visible=False,
                )
                primary["description"] = description.id

            if include_image:
                image = GraphicsNode(
                    kind=NodeKind.IMAGE,
                    name="G2_PRODUCT_IMAGE",
                    visible=False,
                    transform=Transform(
                        x=x + width * 0.05,
                        y=y + height * 0.29,
                        width=width * 0.42,
                        height=height * 0.48,
                    ),
                    style={"fit": "contain", "focus_x": 0.5, "focus_y": 0.5, "zoom": 1.0},
                    metadata={"source": "g2-product-card", "product_card_role": "image"},
                )
                page.add_node(image)
                primary["image"] = image.id

            currency = add_text(
                "price_currency", "price_currency", "R$", 0.50, 0.36, 0.09, 0.10, font_size=16.0
            )
            price = add_text(
                "price", "price_complete", "0,00", 0.59, 0.31, 0.27, 0.17, font_size=34.0
            )
            unit = add_text("unit", "unit", "/UN", 0.86, 0.41, 0.10, 0.08, font_size=13.0)
            primary["price_currency"] = currency.id
            primary["price_complete"] = price.id
            primary["unit"] = unit.id

            next_row = 0.55
            if include_app_price:
                app_currency = add_text(
                    "app_price_currency",
                    "app_price_currency",
                    "R$",
                    0.50,
                    next_row,
                    0.09,
                    0.08,
                    font_size=13.0,
                )
                app_price = add_text(
                    "app_price",
                    "app_price_complete",
                    "0,00",
                    0.59,
                    next_row - 0.02,
                    0.27,
                    0.12,
                    font_size=25.0,
                )
                extra["app_price_currency"] = [app_currency.id]
                extra["app_price_complete"] = [app_price.id]
                next_row += 0.15

            if include_wholesale:
                wholesale_currency = add_text(
                    "wholesale_currency",
                    "wholesale_price_currency",
                    "R$",
                    0.50,
                    next_row,
                    0.09,
                    0.08,
                    font_size=13.0,
                )
                wholesale_price = add_text(
                    "wholesale_price",
                    "wholesale_price",
                    "0,00",
                    0.59,
                    next_row - 0.02,
                    0.27,
                    0.12,
                    font_size=25.0,
                )
                extra["wholesale_price_currency"] = [wholesale_currency.id]
                extra["wholesale_price"] = [wholesale_price.id]

            if include_quantity:
                quantity = add_text(
                    "quantity",
                    "quantity",
                    "",
                    0.50,
                    0.82,
                    0.20,
                    0.08,
                    font_size=14.0,
                    visible=False,
                )
                primary["quantity"] = quantity.id

            if include_validity:
                validity = add_text(
                    "validity",
                    "validity",
                    "",
                    0.71,
                    0.82,
                    0.25,
                    0.08,
                    font_size=12.0,
                    visible=False,
                )
                primary["validity"] = validity.id

            slot = SmartSlot(
                name="ProductCard G2",
                page_id=page.id,
                node_by_role=dict(primary),
                metadata={
                    "source": "g2-product-card",
                    "product_card_runtime_version": 1,
                    "extra_bindings": {role: list(ids) for role, ids in extra.items()},
                },
            )
            page.slots[slot.id] = slot

            semantic_module.build_semantic_blocks(self.document)
            _attach_auxiliary_nodes(semantic_module, page, slot)
            card_id = str(slot.metadata.get("semantic_product_card_id") or "")

        card = page.metadata.get("semantic_blocks", {}).get(card_id, {})
        members = (
            [node_id for node_id in card.get("members", []) if node_id in page.nodes]
            if isinstance(card, dict)
            else []
        )
        self.selection = set(members or primary.values())
        self.anchor_id = name_node.id

        return ProductCardCreation(
            slot_id=slot.id,
            product_card_id=card_id,
            node_by_role=dict(slot.node_by_role),
            extra_bindings={
                str(role): [str(node_id) for node_id in ids]
                for role, ids in dict(slot.metadata.get("extra_bindings") or {}).items()
            },
        )

    def remove_smart_slot(self: Any, slot_id: str, *, delete_nodes: bool = False) -> bool:
        slot = self.page.slots.get(str(slot_id))
        if slot is None or slot.locked:
            return False

        bound_ids = _slot_node_ids(slot)
        with self.transaction("Remover Smart Slot"):
            self.page.slots.pop(slot.id, None)
            if delete_nodes:
                root_ids = [
                    node_id
                    for node_id in bound_ids
                    if node_id in self.page.nodes
                    and not any(node_id in other.children for other in self.page.nodes.values())
                ]
                for node_id in root_ids:
                    if node_id in self.page.nodes:
                        self.page.remove_node(node_id, recursive=True)
            else:
                _clear_unbound_binding_roles(self.page, bound_ids)
            _remove_slot_semantic_blocks(self.page, slot.id)

        self.selection.difference_update(bound_ids)
        if self.anchor_id in bound_ids:
            self.anchor_id = next(iter(self.selection), None)
        return True

    session_type.create_product_card = create_product_card
    session_type.remove_smart_slot = remove_smart_slot
    session_type._sr_product_card_runtime_installed = True


def install_product_card_commands(command_module: Any) -> None:
    router_type = command_module.GraphicsCommandRouter
    if bool(getattr(router_type, "_sr_product_card_commands_installed", False)):
        return

    original_dispatch = router_type.dispatch
    handled = {"create_product_card", "bind_product", "rebind_slot", "remove_smart_slot"}

    def dispatch(self: Any, command: dict[str, Any]):
        name = str(command.get("name") or "").strip().lower()
        if name not in handled:
            return original_dispatch(self, command)
        try:
            if name == "create_product_card":
                created = self.session.create_product_card(
                    x=float(command.get("x", 80.0)),
                    y=float(command.get("y", 80.0)),
                    width=float(command.get("width", 420.0)),
                    height=float(command.get("height", 360.0)),
                    name=str(command.get("product_name") or command.get("name_value") or "Novo produto"),
                    include_image=bool(command.get("include_image", True)),
                    include_description=bool(command.get("include_description", True)),
                    include_quantity=bool(command.get("include_quantity", True)),
                    include_validity=bool(command.get("include_validity", False)),
                    include_app_price=bool(command.get("include_app_price", False)),
                    include_wholesale=bool(command.get("include_wholesale", False)),
                )
                return command_module.CommandResult(
                    True,
                    True,
                    "ProductCard criado.",
                    created.to_dict(),
                )

            if name == "bind_product":
                slot_id = str(command.get("slot_id") or "")
                slot = self.session.page.slots.get(slot_id)
                if slot is None:
                    return command_module.CommandResult(False, False, "Smart Slot não encontrado.")
                if slot.locked:
                    return command_module.CommandResult(False, False, "Smart Slot bloqueado.")

                product = command.get("product")
                if not isinstance(product, dict):
                    product_id = str(command.get("product_id") or "")
                    products = list(self.session.document.metadata.get("products") or [])
                    product = next(
                        (
                            item
                            for item in products
                            if isinstance(item, dict) and str(item.get("id") or "") == product_id
                        ),
                        None,
                    )
                if not isinstance(product, dict):
                    return command_module.CommandResult(False, False, "Produto não encontrado.")

                changed = bool(self.session.bind_product(slot_id, product))
                return command_module.CommandResult(
                    True,
                    changed,
                    "Produto aplicado ao Smart Slot."
                    if changed
                    else "Smart Slot já está atualizado.",
                    {"slot_id": slot_id, "product_id": str(slot.product_id or "")},
                )

            if name == "rebind_slot":
                slot_id = str(command.get("slot_id") or "")
                bindings = command.get("bindings")
                if not isinstance(bindings, dict):
                    return command_module.CommandResult(False, False, "bindings precisa ser um objeto.")
                extras = command.get("extra_bindings")
                if extras is not None and not isinstance(extras, dict):
                    return command_module.CommandResult(
                        False, False, "extra_bindings precisa ser um objeto."
                    )
                changed = bool(
                    self.session.rebind_slot(
                        slot_id,
                        bindings,
                        extra_bindings=extras,
                    )
                )
                return command_module.CommandResult(
                    True,
                    changed,
                    "Smart Slot religado." if changed else "Smart Slot sem alteração.",
                    {"slot_id": slot_id},
                )

            slot_id = str(command.get("slot_id") or "")
            changed = bool(
                self.session.remove_smart_slot(
                    slot_id,
                    delete_nodes=bool(command.get("delete_nodes", False)),
                )
            )
            return command_module.CommandResult(
                True,
                changed,
                "Smart Slot removido." if changed else "Smart Slot não removido.",
                {"slot_id": slot_id},
            )
        except Exception as exc:
            return command_module.CommandResult(False, False, f"{type(exc).__name__}: {exc}")

    router_type.dispatch = dispatch
    router_type._sr_product_card_commands_installed = True


def _attach_auxiliary_nodes(semantic_module: Any, page: Any, slot: Any) -> None:
    card_id = str(slot.metadata.get("semantic_product_card_id") or "")
    blocks = page.metadata.get("semantic_blocks")
    card = blocks.get(card_id) if isinstance(blocks, dict) else None
    if not isinstance(card, dict):
        return

    members = [str(node_id) for node_id in card.get("members") or [] if str(node_id) in page.nodes]
    for role in ("description", "validity"):
        node_id = str(slot.node_by_role.get(role) or "")
        if node_id in page.nodes and node_id not in members:
            members.append(node_id)
            page.nodes[node_id].metadata["semantic_product_card_id"] = card_id
    if not members:
        return

    card["members"] = members
    bounds = semantic_module._bounds_dict(page, members)
    card["bounds"] = bounds
    card["template_geometry"] = {
        node_id: semantic_module._geometry(page.nodes[node_id], bounds) for node_id in members
    }


def _slot_node_ids(slot: Any) -> set[str]:
    result = {str(node_id) for node_id in slot.node_by_role.values() if str(node_id)}
    extras = slot.metadata.get("extra_bindings")
    if isinstance(extras, dict):
        for raw in extras.values():
            if isinstance(raw, str):
                result.add(raw)
            elif isinstance(raw, (list, tuple, set)):
                result.update(str(node_id) for node_id in raw if str(node_id))
    return result


def _clear_unbound_binding_roles(page: Any, node_ids: set[str]) -> None:
    still_bound: set[str] = set()
    for other in page.slots.values():
        still_bound.update(_slot_node_ids(other))
    for node_id in node_ids - still_bound:
        node = page.node(node_id)
        if node is not None:
            node.binding_role = None


def _remove_slot_semantic_blocks(page: Any, slot_id: str) -> None:
    blocks = page.metadata.get("semantic_blocks")
    if not isinstance(blocks, dict):
        return
    removed_ids = {
        block_id
        for block_id, raw in blocks.items()
        if isinstance(raw, dict) and str(raw.get("slot_id") or "") == str(slot_id)
    }
    if not removed_ids:
        return
    for block_id in removed_ids:
        blocks.pop(block_id, None)
    for node in page.nodes.values():
        for key in ("semantic_price_block_id", "semantic_product_card_id"):
            if str(node.metadata.get(key) or "") in removed_ids:
                node.metadata.pop(key, None)
        if str(node.metadata.get("semantic_slot_id") or "") == str(slot_id):
            node.metadata.pop("semantic_slot_id", None)
