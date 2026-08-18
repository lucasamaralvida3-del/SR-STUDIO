from __future__ import annotations

"""Runtime product binding hardening for SR Graphics Engine 2.

The historical binding paths grew independently:

- ``GraphicsSession.bind_product`` handled canonical ``BindingRole`` fields;
- ``CanvaBindingService.bind`` handled Canva/PPTX composite tokens;
- recovered complete prices are represented as ``retail_price``;
- secondary/app/wholesale fields can live in ``SmartSlot.metadata['extra_bindings']``.

This module keeps those public APIs intact while making both paths share the
same product-to-slot contract. The installer is invoked by ``graphics2`` during
package import, before the command router is loaded.
"""

from copy import deepcopy
from typing import Any, Callable, Iterable


_OPTIONAL_TEXT_ROLES = {
    "currency",
    "price_currency",
    "price_reais",
    "price_integer",
    "price_cents",
    "price_complete",
    "unit",
    "limit",
    "app_price",
    "app_price_complete",
    "app_price_currency",
    "app_price_integer",
    "app_price_cents",
    "app_unit",
    "wholesale_price",
    "wholesale_price_currency",
    "wholesale_unit",
    "retail_price",
    "quantity",
    "validity",
    "description",
    "product_description",
}

_IMAGE_ROLES = {"image"}


def install_template_aware_binding_guard(import_module: Any) -> None:
    """Install one coherent binding runtime on the existing public APIs."""

    if bool(getattr(import_module, "_sr_template_binding_guard_installed", False)):
        return

    original: Callable[..., str] = import_module._binding_text

    def guarded_binding_text(role: str, product: dict[str, Any], *, template_text: str = "") -> str:
        role_text = str(role)

        if role_text in {"currency", "price_currency"}:
            whole, _ = import_module._price_parts(_base_price(product))
            return "R$" if whole else ""

        if role_text in {"price_reais", "price_integer"}:
            return import_module._price_parts(_base_price(product))[0]

        if role_text == "price_cents":
            return import_module._price_parts(_base_price(product))[1]

        if role_text == "price_complete":
            return _complete_price_text(import_module, _base_price(product), template_text)

        if role_text == "retail_price":
            return _complete_price_text(import_module, _retail_price(product), template_text)

        if role_text == "wholesale_price":
            return _complete_price_text(import_module, product.get("wholesale_price"), template_text)

        if role_text == "wholesale_price_currency":
            whole, _ = import_module._price_parts(product.get("wholesale_price"))
            return "R$" if whole else ""

        if role_text in {"app_price_complete", "app_price"}:
            return _complete_price_text(import_module, product.get("app_price"), template_text)

        if role_text == "app_price_currency":
            whole, _ = import_module._price_parts(product.get("app_price"))
            return "R$" if whole else ""

        if role_text == "app_price_integer":
            return import_module._price_parts(product.get("app_price"))[0]

        if role_text == "app_price_cents":
            return import_module._price_parts(product.get("app_price"))[1]

        if role_text in {"unit", "app_unit", "wholesale_unit"}:
            if role_text == "app_unit" and not import_module._price_parts(product.get("app_price"))[0]:
                return ""
            if role_text == "wholesale_unit" and not import_module._price_parts(product.get("wholesale_price"))[0]:
                return ""
            return _unit_text(product.get("unit"), template_text)

        if role_text == "quantity":
            return str(product.get("quantity") or "").strip()

        if role_text == "validity":
            return str(product.get("validity") or "").strip()

        if role_text in {"description", "product_description"}:
            metadata = product.get("metadata")
            metadata_description = metadata.get("description") if isinstance(metadata, dict) else ""
            return str(product.get("description") or metadata_description or "").strip()

        return original(role_text, product, template_text=template_text)

    guarded_binding_text.__name__ = original.__name__
    guarded_binding_text.__doc__ = original.__doc__
    guarded_binding_text.__module__ = original.__module__
    import_module._sr_template_binding_original = original
    import_module._binding_text = guarded_binding_text

    _install_session_binding(import_module)
    _install_canva_binding(import_module)
    _install_binding_cleanup(import_module)

    import_module._sr_template_binding_guard_installed = True


def _complete_price_text(import_module: Any, value: object, template_text: str) -> str:
    whole, cents = import_module._price_parts(value)
    if not whole:
        return ""
    amount = f"{whole}{cents}"
    template = str(template_text or "").upper().replace("\u00a0", " ")
    include_currency = not template.strip() or "R$" in template
    return f"R$ {amount}" if include_currency else amount


def _unit_text(value: object, template_text: str) -> str:
    unit = str(value or "UN").upper().strip().lstrip("/")
    if not unit:
        return ""
    template = " ".join(str(template_text or "").upper().replace("\u00a0", " ").split())
    if template == "CADA" and unit in {"UN", "UND", "UNID", "UNIDADE"}:
        return "CADA"
    prefix = "/" if not template or "/" in template else ""
    return f"{prefix}{unit}"


def _base_price(product: dict[str, Any]) -> object:
    value = product.get("price")
    if value in (None, ""):
        value = product.get("retail_price")
    return value


def _retail_price(product: dict[str, Any]) -> object:
    value = product.get("retail_price")
    if value in (None, ""):
        value = product.get("price")
    return value


def _install_session_binding(import_module: Any) -> None:
    session_type = import_module.GraphicsSession
    if bool(getattr(session_type, "_sr_product_binding_runtime_installed", False)):
        return

    original_bind = session_type.bind_product

    def bind_product(self: Any, slot_id: str, product: dict[str, Any]) -> bool:
        slot = self.page.slots.get(str(slot_id))
        if slot is None or slot.locked or not isinstance(product, dict):
            return False

        bindings = _slot_bindings(slot)
        before = _binding_state(self, slot, bindings)

        with self.transaction("Preencher produto"):
            slot.product_id = str(product.get("id") or product.get("product_id") or "")
            slot.metadata["product_snapshot"] = deepcopy(product)

            for role, node_ids in bindings.items():
                for node_id in node_ids:
                    node = self.page.node(node_id)
                    if node is None:
                        continue
                    _reactivate_binding_node(node)
                    if role in _IMAGE_ROLES:
                        _bind_image(import_module, self, node, product)
                        continue
                    if node.kind is not import_module.NodeKind.TEXT:
                        continue

                    _assign_binding_role(import_module, node, role)
                    template_text = _stable_template_text(node)
                    value = import_module._binding_text(role, product, template_text=template_text)
                    node.text = value
                    if role in _OPTIONAL_TEXT_ROLES:
                        node.visible = bool(value)
                    elif value:
                        node.visible = True

        after = _binding_state(self, slot, bindings)
        return before != after

    bind_product.__name__ = original_bind.__name__
    bind_product.__doc__ = original_bind.__doc__
    bind_product.__module__ = original_bind.__module__
    session_type._sr_product_binding_original = original_bind
    session_type.bind_product = bind_product

    def rebind_slot(
        self: Any,
        slot_id: str,
        bindings: dict[Any, str | Iterable[str]],
        *,
        extra_bindings: dict[Any, Iterable[str]] | None = None,
    ) -> bool:
        slot = self.page.slots.get(str(slot_id))
        if slot is None or slot.locked:
            return False

        primary: dict[str, str] = {}
        extras: dict[str, list[str]] = {}

        for raw_role, raw_nodes in dict(bindings or {}).items():
            role = _role_text(raw_role)
            node_ids = _node_id_list(raw_nodes)
            if not node_ids:
                continue
            _assert_nodes_exist(self.page, node_ids)
            primary[role] = node_ids[0]
            if len(node_ids) > 1:
                extras.setdefault(role, []).extend(node_ids[1:])

        for raw_role, raw_nodes in dict(extra_bindings or {}).items():
            role = _role_text(raw_role)
            node_ids = _node_id_list(raw_nodes)
            _assert_nodes_exist(self.page, node_ids)
            if node_ids:
                extras.setdefault(role, []).extend(node_ids)

        extras = {role: _unique(ids) for role, ids in extras.items() if ids}
        current_primary = dict(slot.node_by_role)
        current_extras = _normalized_extras(slot.metadata.get("extra_bindings"))
        bound_ids = _unique([*primary.values(), *(item for ids in extras.values() for item in ids)])
        detached = any(
            bool(self.page.node(node_id).metadata.get("smart_slot_detached"))
            for node_id in bound_ids
            if self.page.node(node_id) is not None
        )
        if current_primary == primary and current_extras == extras and not detached:
            return False

        with self.transaction("Religar Smart Slot"):
            slot.node_by_role = dict(primary)
            if extras:
                slot.metadata["extra_bindings"] = deepcopy(extras)
            else:
                slot.metadata.pop("extra_bindings", None)
            for role, node_id in primary.items():
                node = self.page.node(node_id)
                if node is not None:
                    _reactivate_binding_node(node)
                    _assign_binding_role(import_module, node, role)
            for node_ids in extras.values():
                for node_id in node_ids:
                    node = self.page.node(node_id)
                    if node is not None:
                        _reactivate_binding_node(node)

        return True

    session_type.rebind_slot = rebind_slot
    session_type._sr_product_binding_runtime_installed = True


def _install_canva_binding(import_module: Any) -> None:
    service = import_module.CanvaBindingService
    if bool(getattr(service, "_sr_product_binding_runtime_installed", False)):
        return

    original = service.bind

    @staticmethod
    def bind(session: Any, slot_id: str, product: dict[str, Any]) -> bool:
        return bool(session.bind_product(slot_id, product))

    service._sr_product_binding_original = original
    service.bind = bind
    service._sr_product_binding_runtime_installed = True


def _install_binding_cleanup(import_module: Any) -> None:
    page_type = import_module.GraphicsPage
    if bool(getattr(page_type, "_sr_binding_cleanup_installed", False)):
        return

    original = page_type.remove_node

    def remove_node(self: Any, node_id: str, *, recursive: bool = True):
        removed = original(self, node_id, recursive=recursive)
        removed_ids = {str(node.id) for node in removed}
        if not removed_ids:
            return removed

        for slot in self.slots.values():
            extras = _normalized_extras(slot.metadata.get("extra_bindings"))
            cleaned = {
                role: [bound_id for bound_id in node_ids if bound_id not in removed_ids]
                for role, node_ids in extras.items()
            }
            cleaned = {role: node_ids for role, node_ids in cleaned.items() if node_ids}
            if cleaned:
                slot.metadata["extra_bindings"] = cleaned
            else:
                slot.metadata.pop("extra_bindings", None)

            for key in (
                "primary_price_node_id",
                "secondary_price_node_id",
                "wholesale_price_node_id",
                "wholesale_currency_node_id",
                "quantity_node_id",
                "limit_node_id",
            ):
                if str(slot.metadata.get(key) or "") in removed_ids:
                    slot.metadata[key] = ""

        return removed

    remove_node.__name__ = original.__name__
    remove_node.__doc__ = original.__doc__
    remove_node.__module__ = original.__module__
    page_type._sr_binding_cleanup_original = original
    page_type.remove_node = remove_node
    page_type._sr_binding_cleanup_installed = True


def _slot_bindings(slot: Any) -> dict[str, list[str]]:
    bindings: dict[str, list[str]] = {}
    for raw_role, node_id in slot.node_by_role.items():
        if node_id:
            bindings.setdefault(_role_text(raw_role), []).append(str(node_id))
    for role, node_ids in _normalized_extras(slot.metadata.get("extra_bindings")).items():
        bindings.setdefault(role, []).extend(node_ids)
    return {role: _unique(node_ids) for role, node_ids in bindings.items()}


def _stable_template_text(node: Any) -> str:
    stored = node.metadata.get("binding_template_text")
    if stored is not None:
        return str(stored)

    template = node.metadata.get("template_text")
    if template is None and str(node.metadata.get("source") or "").lower() == "pptx":
        template = node.text
    value = str(template or "")
    node.metadata["binding_template_text"] = value
    return value


def _bind_image(import_module: Any, session: Any, node: Any, product: dict[str, Any]) -> None:
    source = str(
        product.get("image_path")
        or product.get("image")
        or product.get("image_uri")
        or ""
    ).strip()
    requested_asset_id = str(product.get("image_asset_id") or "").strip()

    node.metadata["binding_managed_image"] = True
    if source:
        node.asset_id = import_module._ensure_asset(session.document, source)
        node.metadata["bound_image_source"] = source
        node.visible = True
        return

    if requested_asset_id and requested_asset_id in session.document.assets:
        node.asset_id = requested_asset_id
        node.metadata.pop("bound_image_source", None)
        node.visible = True
        return

    # A slot is a product-owned image surface. When a replacement product has
    # no usable image, retaining the previous product photo is a data error.
    node.asset_id = ""
    node.metadata.pop("bound_image_source", None)
    node.visible = False


def _reactivate_binding_node(node: Any) -> None:
    node.metadata.pop("smart_slot_detached", None)
    node.metadata.pop("detached_from_slot_id", None)


def _assign_binding_role(import_module: Any, node: Any, role: str) -> None:
    try:
        node.binding_role = import_module.BindingRole(role)
    except (TypeError, ValueError):
        # Composite Canva/PPTX tokens are valid slot roles without expanding
        # the canonical enum or changing the SR Scene serializer schema.
        pass


def _binding_state(session: Any, slot: Any, bindings: dict[str, list[str]]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_ids in bindings.values():
        for node_id in node_ids:
            node = session.page.node(node_id)
            if node is None:
                continue
            nodes[node_id] = (
                str(node.text),
                str(node.asset_id),
                bool(node.visible),
                deepcopy(node.metadata.get("bound_image_source")),
                deepcopy(node.metadata.get("binding_template_text")),
                bool(node.metadata.get("smart_slot_detached")),
                str(node.metadata.get("detached_from_slot_id") or ""),
            )
    return {
        "product_id": str(slot.product_id or ""),
        "product_snapshot": deepcopy(slot.metadata.get("product_snapshot")),
        "nodes": nodes,
    }


def _role_text(role: Any) -> str:
    return str(getattr(role, "value", role))


def _node_id_list(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value if str(item)]


def _assert_nodes_exist(page: Any, node_ids: Iterable[str]) -> None:
    missing = [node_id for node_id in node_ids if node_id not in page.nodes]
    if missing:
        raise KeyError(f"Node do slot inexistente: {missing[0]}")


def _normalized_extras(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for raw_role, raw_nodes in value.items():
        role = _role_text(raw_role)
        if isinstance(raw_nodes, (list, tuple, set)):
            node_ids = [str(node_id) for node_id in raw_nodes if str(node_id)]
        elif raw_nodes:
            node_ids = [str(raw_nodes)]
        else:
            node_ids = []
        if node_ids:
            result[role] = _unique(node_ids)
    return result


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))
