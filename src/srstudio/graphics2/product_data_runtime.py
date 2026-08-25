from __future__ import annotations

"""Dynamic product-data updates and production-source composition for G2.

Besides editing/cascading product data, this runtime owns the user-facing
composition contract:

- Canva/PPTX supplies the visual template and Smart Slots;
- XLSX/XLSM supplies the active product catalog;
- both can be imported in either order inside the same editor session.

Importing a spreadsheet never replaces pages/artwork. Importing a template
replaces the visual document while preserving the already-loaded product
catalog. This keeps the two sources complementary instead of competing entry
paths.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
import os

from srstudio.images.library import ImageLibrary

from . import binding_runtime as binding_runtime
from . import import_bridge as import_bridge


@dataclass(slots=True)
class ProductUpdateResult:
    changed: bool
    product_id: str
    slots_updated: int = 0
    slots_skipped_locked: int = 0
    catalog_updated: bool = False
    page_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["page_ids"] = list(self.page_ids or [])
        return result


def _product_image_library() -> ImageLibrary:
    """Return the same persistent product-image bank used by the full Studio."""

    return ImageLibrary(Path.home() / ".srstudio5" / "images")


def _product_import_service() -> Any:
    return import_bridge.GraphicsImportService(image_library=_product_image_library())


def install_product_data_runtime(session_type: Any, command_module: Any) -> None:
    if not bool(getattr(session_type, "_sr_product_data_runtime_installed", False)):
        _install_session_methods(session_type)
        session_type._sr_product_data_runtime_installed = True
    _install_commands(command_module)


def _install_session_methods(session_type: Any) -> None:
    def update_product_fields(
        self: Any,
        slot_id: str,
        changes: dict[str, Any],
    ) -> ProductUpdateResult:
        slot = self.page.slots.get(str(slot_id))
        if slot is None:
            raise KeyError(f"Smart Slot inexistente: {slot_id}")
        if slot.locked:
            return ProductUpdateResult(False, str(slot.product_id or ""), slots_skipped_locked=1)
        if not isinstance(changes, dict):
            raise TypeError("changes precisa ser um objeto")

        product_id = str(slot.product_id or "")
        base = slot.metadata.get("product_snapshot")
        product = deepcopy(base) if isinstance(base, dict) else {}
        product = _merge_product(product, changes)
        if product_id:
            product["id"] = product_id

        changed = False
        with self.transaction("Atualizar campos do produto"):
            changed = _apply_product_to_slot(self, self.page, slot, product)

        return ProductUpdateResult(
            changed=changed,
            product_id=str(slot.product_id or product_id),
            slots_updated=1 if changed else 0,
            page_ids=[self.page.id] if changed else [],
        )

    def update_product_data(
        self: Any,
        product_id: str,
        changes: dict[str, Any],
        *,
        cascade: bool = True,
    ) -> ProductUpdateResult:
        product_id = str(product_id or "").strip()
        if not product_id:
            raise ValueError("product_id ausente")
        if not isinstance(changes, dict):
            raise TypeError("changes precisa ser um objeto")

        targets = [
            (page, slot)
            for page in self.document.pages
            for slot in page.slots.values()
            if str(slot.product_id or "") == product_id
        ]
        catalog, catalog_index = _catalog_product(self.document, product_id)
        if catalog is not None:
            base = catalog
        else:
            snapshot = next(
                (
                    slot.metadata.get("product_snapshot")
                    for _, slot in targets
                    if isinstance(slot.metadata.get("product_snapshot"), dict)
                ),
                None,
            )
            base = deepcopy(snapshot) if isinstance(snapshot, dict) else {"id": product_id}

        product = _merge_product(base, changes)
        product["id"] = product_id
        changed = False
        slots_updated = 0
        skipped_locked = 0
        changed_pages: list[str] = []
        catalog_updated = False

        with self.transaction("Atualizar produto em cascata"):
            if catalog_index is not None:
                products = self.document.metadata.get("products")
                if isinstance(products, list) and products[catalog_index] != product:
                    products[catalog_index] = deepcopy(product)
                    catalog_updated = True
                    changed = True

            if cascade:
                for page, slot in targets:
                    if slot.locked:
                        skipped_locked += 1
                        continue
                    slot_changed = _apply_product_to_slot(self, page, slot, product)
                    if not slot_changed:
                        continue
                    slots_updated += 1
                    changed = True
                    if page.id not in changed_pages:
                        changed_pages.append(page.id)

        return ProductUpdateResult(
            changed=changed,
            product_id=product_id,
            slots_updated=slots_updated,
            slots_skipped_locked=skipped_locked,
            catalog_updated=catalog_updated,
            page_ids=changed_pages,
        )

    def import_product_catalog(self: Any, source: str) -> dict[str, Any]:
        path = _source_path(source)
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("Selecione uma planilha XLSX/XLSM de produtos.")
        imported = _product_import_service().import_file(path, project_name=path.stem)
        products = imported.document.metadata.get("products")
        if not isinstance(products, list):
            products = []
        products = [deepcopy(item) for item in products if isinstance(item, dict)]
        if not products:
            raise ValueError("A planilha não produziu nenhum produto reconhecido.")

        previous = deepcopy(self.document.metadata.get("products") or [])
        with self.transaction("Importar planilha de produtos"):
            self.document.metadata["products"] = products
            self.document.metadata["product_catalog_source"] = str(path)
            self.document.metadata["product_catalog_count"] = len(products)
            self.document.metadata["product_catalog_import_mode"] = "spreadsheet-overlay"

        return {
            "changed": previous != products,
            "products": len(products),
            "source": str(path),
            "pages_preserved": len(self.document.pages),
            "template_preserved": True,
        }

    def import_template_source(self: Any, source: str) -> dict[str, Any]:
        path = _source_path(source)
        if path.suffix.lower() != ".pptx":
            raise ValueError("Selecione um arquivo Canva/PowerPoint em formato PPTX.")

        catalog = [
            deepcopy(item)
            for item in (self.document.metadata.get("products") or [])
            if isinstance(item, dict)
        ]
        catalog_source = str(self.document.metadata.get("product_catalog_source") or "")
        imported = import_bridge.GraphicsImportService().import_file(path, project_name=path.stem)
        replacement = imported.document

        # Fresh PPTX import has already run Smart Slot visual reset. Reattach only
        # the external catalog; never reattach products inferred from the template.
        replacement.metadata["products"] = catalog
        replacement.metadata["template_source"] = str(path)
        replacement.metadata["template_import_mode"] = "replace-layout-preserve-catalog"
        if catalog_source:
            replacement.metadata["product_catalog_source"] = catalog_source
        replacement.metadata["product_catalog_count"] = len(catalog)

        self.document = replacement
        self.history.clear()
        self.clear_selection()

        return {
            "changed": True,
            "source": str(path),
            "products_preserved": len(catalog),
            "pages": len(replacement.pages),
            "slots": sum(len(page.slots) for page in replacement.pages),
            "template_started_empty": bool(replacement.metadata.get("smart_slot_import_started_empty")),
        }

    session_type.update_product_fields = update_product_fields
    session_type.update_product_data = update_product_data
    session_type.import_product_catalog = import_product_catalog
    session_type.import_template_source = import_template_source


def _install_commands(command_module: Any) -> None:
    router_type = command_module.GraphicsCommandRouter
    if bool(getattr(router_type, "_sr_product_data_commands_installed", False)):
        return

    original_dispatch = router_type.dispatch

    def dispatch(self: Any, command: dict[str, Any]):
        name = str(command.get("name") or "").strip().lower()
        managed = {
            "update_product_fields",
            "update_product_data",
            "import_product_catalog",
            "import_template_source",
        }
        if name not in managed:
            return original_dispatch(self, command)
        try:
            if name == "import_product_catalog":
                result = self.session.import_product_catalog(str(command.get("path") or command.get("source") or ""))
                return command_module.CommandResult(
                    True,
                    bool(result.get("changed", True)),
                    f"Planilha carregada · {result['products']} produto(s) disponíveis no mesmo projeto.",
                    result,
                )

            if name == "import_template_source":
                result = self.session.import_template_source(str(command.get("path") or command.get("source") or ""))
                return command_module.CommandResult(
                    True,
                    True,
                    f"Canva/PPTX carregado · {result['slots']} Smart Slot(s) · {result['products_preserved']} produto(s) preservados da planilha.",
                    result,
                )

            changes = command.get("changes")
            if not isinstance(changes, dict):
                return command_module.CommandResult(False, False, "changes precisa ser um objeto.")

            if name == "update_product_fields":
                slot_id = str(command.get("slot_id") or "")
                result = self.session.update_product_fields(slot_id, changes)
                return command_module.CommandResult(
                    True,
                    result.changed,
                    "Campos do ProductCard atualizados."
                    if result.changed
                    else "ProductCard sem alteração.",
                    result.to_dict(),
                )

            product_id = str(command.get("product_id") or "")
            result = self.session.update_product_data(
                product_id,
                changes,
                cascade=bool(command.get("cascade", True)),
            )
            return command_module.CommandResult(
                True,
                result.changed,
                "Produto atualizado em cascata."
                if result.changed
                else "Produto sem alteração.",
                result.to_dict(),
            )
        except Exception as exc:
            return command_module.CommandResult(False, False, f"{type(exc).__name__}: {exc}")

    router_type.dispatch = dispatch
    router_type._sr_product_data_commands_installed = True


def _source_path(raw: str) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("Arquivo não informado.")
    parsed = urlparse(value)
    if parsed.scheme.lower() == "file":
        path_text = unquote(parsed.path or "")
        if parsed.netloc:
            path_text = f"//{parsed.netloc}{path_text}"
        if os.name == "nt" and len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
            path_text = path_text[1:]
        path = Path(path_text)
    else:
        path = Path(value)
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    return path


def _apply_product_to_slot(session: Any, page: Any, slot: Any, product: dict[str, Any]) -> bool:
    bindings = binding_runtime._slot_bindings(slot)
    before = _slot_state(page, slot, bindings)

    slot.product_id = str(product.get("id") or product.get("product_id") or slot.product_id or "")
    slot.metadata["product_snapshot"] = deepcopy(product)

    for role, node_ids in bindings.items():
        for node_id in node_ids:
            node = page.node(node_id)
            if node is None:
                continue
            binding_runtime._reactivate_binding_node(node)
            if role in binding_runtime._IMAGE_ROLES:
                binding_runtime._bind_image(import_bridge, session, node, product)
                continue
            if node.kind is not import_bridge.NodeKind.TEXT:
                continue

            binding_runtime._assign_binding_role(import_bridge, node, role)
            template_text = binding_runtime._stable_template_text(node)
            value = import_bridge._binding_text(role, product, template_text=template_text)
            node.text = value
            if role in binding_runtime._OPTIONAL_TEXT_ROLES:
                node.visible = bool(value)
            elif value:
                node.visible = True

    return before != _slot_state(page, slot, bindings)


def _slot_state(page: Any, slot: Any, bindings: dict[str, list[str]]) -> dict[str, Any]:
    nodes: dict[str, Any] = {}
    for node_ids in bindings.values():
        for node_id in node_ids:
            node = page.node(node_id)
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


def _catalog_product(document: Any, product_id: str) -> tuple[dict[str, Any] | None, int | None]:
    products = document.metadata.get("products")
    if not isinstance(products, list):
        return None, None
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            continue
        if str(product.get("id") or "") == product_id:
            return deepcopy(product), index
    return None, None


def _merge_product(base: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    product = deepcopy(base)
    metadata_change = changes.get("metadata")
    for key, value in changes.items():
        if key == "metadata" and isinstance(metadata_change, dict):
            current = product.get("metadata")
            merged_metadata = deepcopy(current) if isinstance(current, dict) else {}
            merged_metadata.update(deepcopy(metadata_change))
            product["metadata"] = merged_metadata
        else:
            product[str(key)] = deepcopy(value)
    return product
