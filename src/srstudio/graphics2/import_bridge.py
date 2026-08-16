from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from srstudio.core.models import StudioProject
from srstudio.importers.pipeline import ImportSummary, UnifiedImportPipeline

from .compat import from_studio_project
from .import_audit import ImportAuditReport, audit_import
from .model import AssetRef, BindingRole, CoordinateUnit, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, SmartSlot, Transform
from .operations import GraphicsSession, _price_parts

_SLOT_ROLE_MAP: dict[str, BindingRole] = {
    "name": BindingRole.NAME,
    "image": BindingRole.IMAGE,
    "price_currency": BindingRole.CURRENCY,
    "price_integer": BindingRole.PRICE_REAIS,
    "price_cents": BindingRole.PRICE_CENTS,
    "unit": BindingRole.UNIT,
    "limit": BindingRole.LIMIT,
    "app_price_complete": BindingRole.APP_PRICE,
}


@dataclass(slots=True)
class GraphicsImportResult:
    document: GraphicsDocument
    summary: ImportSummary
    legacy_project: StudioProject
    audit: ImportAuditReport


class GraphicsImportService:
    """Reutiliza os importadores maduros do SR Studio e troca apenas o destino."""

    def __init__(self, *, image_library=None, layout_corpus=None) -> None:
        self.pipeline = UnifiedImportPipeline(image_library=image_library, layout_corpus=layout_corpus)

    def import_file(self, path: str | Path, *, project_name: str = "Novo Projeto SR") -> GraphicsImportResult:
        project = StudioProject(name=project_name)
        summary = self.pipeline.import_file(path, project)
        document = from_imported_project(project)
        document.metadata["import_summary"] = {
            "source": summary.source,
            "products_added": summary.products_added,
            "cards_added": summary.cards_added,
            "images_matched": summary.images_matched,
            "images_learned": summary.images_learned,
            "layouts_learned": summary.layouts_learned,
            "warnings": list(summary.warnings),
        }
        audit = audit_import(document)
        return GraphicsImportResult(document=document, summary=summary, legacy_project=project, audit=audit)


def from_imported_project(project: StudioProject) -> GraphicsDocument:
    document = from_studio_project(project)
    document.metadata["products"] = [product.to_dict() for product in project.products]
    document.metadata["graphics2_import_bridge"] = 2
    for index, old_page in enumerate(project.pages):
        if not old_page.elements:
            continue
        converted = _convert_visual_page(document, old_page, project)
        if converted.nodes:
            document.pages[index] = converted
    if document.pages and document.page(document.active_page_id) is None:
        document.active_page_id = document.pages[0].id
    audit_import(document, check_local_assets=False)
    return document


def _convert_visual_page(document: GraphicsDocument, old_page, project: StudioProject) -> GraphicsPage:
    page = GraphicsPage(
        id=old_page.id,
        name=old_page.name,
        width=float(old_page.width),
        height=float(old_page.height),
        unit=CoordinateUnit.PIXEL,
        background=old_page.background,
        metadata={
            "source": "srstudio-import-pipeline",
            "canva_native_visual": bool(project.settings.get("canva_native_visual")),
            "canva_import_version": project.settings.get("canva_import_version"),
            "canva_rendering_version": project.settings.get("canva_rendering_version"),
        },
    )
    slot_nodes: dict[str, dict[str, list[str]]] = {}
    for index, element in enumerate(old_page.elements):
        node = _element_to_node(document, element, index)
        if node is None:
            continue
        page.add_node(node)
        slot_id = str(element.get("slot_id") or "")
        slot_role = str(element.get("slot_role") or "")
        if slot_id and slot_role:
            slot_nodes.setdefault(slot_id, {}).setdefault(slot_role, []).append(node.id)

    card_by_id = {card.id: card for card in old_page.cards}
    for slot_id, bindings in slot_nodes.items():
        card = card_by_id.get(slot_id)
        product = next((item for item in project.products if card is not None and item.id == card.product_id), None)
        primary: dict[str, str] = {}
        extras: dict[str, list[str]] = {}
        for raw_role, node_ids in bindings.items():
            mapped = _SLOT_ROLE_MAP.get(raw_role)
            if mapped is not None and node_ids:
                primary[mapped.value] = node_ids[0]
                if len(node_ids) > 1:
                    extras[raw_role] = node_ids[1:]
            else:
                extras[raw_role] = list(node_ids)
        slot = SmartSlot(
            id=slot_id,
            name=f"Produto {len(page.slots) + 1}",
            page_id=page.id,
            node_by_role=primary,
            product_id=(card.product_id if card is not None else ""),
            confidence=float((card.overrides.get("recognition_confidence", 1.0) if card is not None else 1.0) or 1.0),
            metadata={
                "extra_bindings": extras,
                "product_snapshot": product.to_dict() if product is not None else {},
                "source": "canva-smart-slot",
            },
        )
        page.slots[slot.id] = slot
    return page


def _element_to_node(document: GraphicsDocument, element: dict[str, Any], index: int) -> GraphicsNode | None:
    kind_map = {
        "text": NodeKind.TEXT,
        "image": NodeKind.IMAGE,
        "rect": NodeKind.RECT,
        "line": NodeKind.LINE,
        "ellipse": NodeKind.ELLIPSE,
        "path": NodeKind.PATH,
    }
    kind = kind_map.get(str(element.get("type") or ""))
    if kind is None:
        return None
    slot_id = str(element.get("slot_id") or "")
    slot_role = str(element.get("slot_role") or "")
    mapped_role = _SLOT_ROLE_MAP.get(slot_role)
    style = _style_from_element(element, kind)
    source = str(element.get("path") or "")
    asset_id = _ensure_asset(document, source) if kind is NodeKind.IMAGE and source else ""
    metadata = {
        "source": str(element.get("source") or ""),
        "source_name": str(element.get("name") or ""),
        "slot_id": slot_id,
        "slot_role": slot_role,
        "template_hidden": bool(element.get("template_hidden", element.get("hidden", False))),
        "grouped": bool(element.get("grouped", False)),
        "group_depth": int(element.get("group_depth", 0) or 0),
        "source_font_name": str(element.get("source_font_name") or ""),
        "shape_geometry": str(element.get("shape_geometry") or ""),
    }
    if source:
        metadata["bound_image_source"] = source
    if "template_text" in element:
        metadata["template_text"] = str(element.get("template_text") or "")
    if "template_path" in element:
        metadata["template_path"] = str(element.get("template_path") or "")
    return GraphicsNode(
        kind=kind,
        name=str(element.get("name") or f"Elemento {index + 1}"),
        transform=Transform(
            x=float(element.get("x", 0) or 0),
            y=float(element.get("y", 0) or 0),
            width=max(0.0, float(element.get("width", 0) or 0)),
            height=max(0.0, float(element.get("height", 0) or 0)),
            rotation=float(element.get("rotation", 0) or 0),
        ),
        z_index=int(element.get("z_index", index) or index),
        locked=not bool(slot_id),
        visible=not bool(element.get("hidden", False)),
        opacity=min(1.0, max(0.0, float(element.get("opacity", 1.0) or 1.0))),
        text=str(element.get("text") or "") if kind is NodeKind.TEXT else "",
        asset_id=asset_id,
        binding_role=mapped_role,
        style=style,
        metadata=metadata,
    )


def _style_from_element(element: dict[str, Any], kind: NodeKind) -> dict[str, Any]:
    if kind is NodeKind.TEXT:
        return {
            "font_family": str(element.get("font_name") or element.get("source_font_name") or "Segoe UI"),
            "source_font_family": str(element.get("source_font_name") or element.get("font_name") or ""),
            "font_size": float(element.get("font_size", 20) or 20),
            "font_weight": 700 if bool(element.get("bold")) else 400,
            "italic": bool(element.get("italic")),
            "color": str(element.get("fill") or "#162033"),
            "align": str(element.get("align") or "left"),
            "v_align": str(element.get("vertical_anchor") or "center"),
            "nowrap": bool(element.get("canva_no_wrap") or element.get("canva_single_line")),
            "fit_inside_box": bool(element.get("canva_fit_inside_box")),
        }
    if kind is NodeKind.IMAGE:
        return {
            "fit": str(element.get("image_fit") or "contain"),
            "crop": dict(element.get("crop") or {}),
            "fill_rect": dict(element.get("fill_rect") or {}),
            "flip_x": bool(element.get("flip_h")),
            "flip_y": bool(element.get("flip_v")),
            "zoom": 1.0,
            "focus_x": 0.5,
            "focus_y": 0.5,
        }
    if kind in {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.PATH}:
        return {
            "fill": str(element.get("fill") or "transparent"),
            "stroke": str(element.get("outline") or "transparent"),
            "stroke_width": float(element.get("line_width", 0) or 0),
            "radius_ratio": float(element.get("corner_radius_ratio", 0) or 0),
        }
    if kind is NodeKind.LINE:
        return {
            "stroke": str(element.get("outline") or element.get("fill") or "#000000"),
            "stroke_width": float(element.get("line_width", 1) or 1),
        }
    return {}


def _ensure_asset(document: GraphicsDocument, source: str) -> str:
    for asset in document.assets.values():
        if asset.source == source:
            return asset.id
    asset = AssetRef(kind="image", source=source, embedded=False, metadata={"source": "import-pipeline"})
    document.assets[asset.id] = asset
    return asset.id


class CanvaBindingService:
    """Preenche todos os tokens Canva, inclusive os papéis legados compostos."""

    @staticmethod
    def bind(session: GraphicsSession, slot_id: str, product: dict[str, Any]) -> bool:
        slot = session.page.slots.get(slot_id)
        if slot is None or slot.locked:
            return False
        bindings: dict[str, list[str]] = {}
        for role, node_id in slot.node_by_role.items():
            bindings.setdefault(role, []).append(node_id)
        for role, node_ids in dict(slot.metadata.get("extra_bindings") or {}).items():
            bindings.setdefault(str(role), []).extend(str(node_id) for node_id in node_ids)
        with session.transaction("Preencher produto Canva"):
            slot.product_id = str(product.get("id") or product.get("product_id") or "")
            slot.metadata["product_snapshot"] = dict(product)
            for role, node_ids in bindings.items():
                for node_id in node_ids:
                    node = session.page.node(node_id)
                    if node is None:
                        continue
                    if role in {"image", BindingRole.IMAGE.value}:
                        source = str(product.get("image_path") or product.get("image") or "")
                        if source:
                            node.asset_id = _ensure_asset(session.document, source)
                            node.metadata["bound_image_source"] = source
                            node.visible = True
                        continue
                    if node.kind is not NodeKind.TEXT:
                        continue
                    value = _binding_text(role, product)
                    node.text = value
                    if role in {
                        "limit",
                        "app_price_complete",
                        "app_price_currency",
                        "app_price_integer",
                        "app_price_cents",
                    }:
                        node.visible = bool(value)
                    elif value:
                        node.visible = True
        return True


def _binding_text(role: str, product: dict[str, Any]) -> str:
    role = str(role)
    if role in {"name", BindingRole.NAME.value}:
        return str(product.get("display_name") or product.get("name") or product.get("original_name") or "")
    if role in {"price_currency", BindingRole.CURRENCY.value}:
        return "R$"
    if role in {"price_integer", BindingRole.PRICE_REAIS.value}:
        return _price_parts(product.get("price"))[0]
    if role in {"price_cents", BindingRole.PRICE_CENTS.value}:
        return _price_parts(product.get("price"))[1]
    if role == "price_complete":
        whole, cents = _price_parts(product.get("price"))
        return f"R$ {whole}{cents}" if whole else ""
    if role in {"unit", BindingRole.UNIT.value}:
        unit = str(product.get("unit") or "UN").upper().strip().lstrip("/")
        return f"/{unit}" if unit else ""
    if role in {"limit", BindingRole.LIMIT.value}:
        limit = str(product.get("cpf_limit") or product.get("limit") or "").strip()
        return f"LIMITE DE {limit} POR CPF" if limit else ""
    if role == "app_price_currency":
        return "R$" if product.get("app_price") not in (None, "") else ""
    if role == "app_price_integer":
        return _price_parts(product.get("app_price"))[0]
    if role == "app_price_cents":
        return _price_parts(product.get("app_price"))[1]
    if role in {"app_price_complete", BindingRole.APP_PRICE.value}:
        whole, cents = _price_parts(product.get("app_price"))
        return f"R$ {whole}{cents}" if whole else ""
    if role == "app_unit":
        unit = str(product.get("unit") or "UN").upper().strip().lstrip("/")
        return f"/{unit}" if unit and product.get("app_price") not in (None, "") else ""
    return ""