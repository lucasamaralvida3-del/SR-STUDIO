from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from srstudio.core.models import StudioProject

from .legacy_sync import LEGACY_SOURCE_FINGERPRINT_KEY, fingerprint_studio_project
from .model import BindingRole, CoordinateUnit, GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, SmartSlot, Transform, _id


def from_studio_project(project: StudioProject) -> GraphicsDocument:
    pages: list[GraphicsPage] = []
    products = {product.id: product for product in project.products}
    product_payloads = [product.to_dict() for product in project.products]
    source_fingerprint = fingerprint_studio_project(project)
    for old_page in project.pages:
        page = GraphicsPage(
            id=old_page.id,
            name=old_page.name,
            width=old_page.width,
            height=old_page.height,
            unit=CoordinateUnit.PIXEL,
            background=old_page.background,
            metadata={
                "legacy_elements": list(old_page.elements),
                "migrated_from": "srstudio/1",
            },
        )
        for card in old_page.cards:
            product = products.get(card.product_id)
            _append_card(page, card, product.to_dict() if product else {"id": card.product_id})
        pages.append(page)
    return GraphicsDocument(
        name=project.name,
        pages=pages or [GraphicsPage()],
        active_page_id=(pages[0].id if pages else ""),
        metadata={
            "campaign": project.campaign,
            "legacy_project_id": project.id,
            "legacy_schema_version": project.schema_version,
            "legacy_settings": dict(project.settings),
            "products": product_payloads,
            "graphics2_bridge_source": "studio-project-5x",
            LEGACY_SOURCE_FINGERPRINT_KEY: source_fingerprint,
        },
    )


def _price_parts(value: Any) -> tuple[str, str]:
    if value in (None, ""):
        return "", ""
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return "", ""
    whole, cents = f"{amount:.2f}".split(".")
    return whole, f",{cents}"


def _append_card(page: GraphicsPage, card: Any, product: dict[str, Any]) -> None:
    x, y, w, h = float(card.x), float(card.y), float(card.width), float(card.height)
    group = GraphicsNode(
        id=card.id,
        kind=NodeKind.GROUP,
        name=str(product.get("display_name") or product.get("name") or "Produto"),
        transform=Transform(x=x, y=y, width=w, height=h, rotation=float(card.rotation)),
        locked=bool(card.locked),
        z_index=int(card.z_index),
        metadata={
            "legacy_product_id": card.product_id,
            "legacy_style_id": card.style_id,
            "legacy_highlighted": bool(card.highlighted),
            "legacy_overrides": dict(card.overrides),
        },
    )
    page.add_node(group)
    name_h = max(24.0, h * 0.18)
    price_h = max(36.0, h * 0.28)
    image_h = max(20.0, h - name_h - price_h)
    image_source = str(product.get("image_path") or product.get("image") or "")
    image = GraphicsNode(
        kind=NodeKind.IMAGE,
        name="Imagem do produto",
        transform=Transform(x=x, y=y + name_h, width=w, height=image_h),
        binding_role=BindingRole.IMAGE,
        style={"fit": "contain", "focus_x": 0.5, "focus_y": 0.5, "zoom": 1.0},
        metadata={"bound_image_source": image_source} if image_source else {},
    )
    name = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Nome do produto",
        text=str(product.get("display_name") or product.get("name") or product.get("original_name") or ""),
        transform=Transform(x=x, y=y, width=w, height=name_h),
        binding_role=BindingRole.NAME,
        style={"font_family": "Segoe UI", "font_size": 20.0, "font_weight": 800, "align": "center"},
    )
    currency_w = max(24.0, w * 0.12)
    cents_w = max(30.0, w * 0.18)
    unit_w = max(34.0, w * 0.16)
    whole_w = max(40.0, w - currency_w - cents_w - unit_w)
    price_y = y + h - price_h
    whole_text, cents_text = _price_parts(product.get("price"))
    unit_text = str(product.get("unit") or "UN").upper().strip()
    if unit_text and not unit_text.startswith("/"):
        unit_text = f"/{unit_text}"
    currency = GraphicsNode(
        kind=NodeKind.TEXT,
        name="R$",
        text="R$",
        transform=Transform(x=x, y=price_y, width=currency_w, height=price_h),
        binding_role=BindingRole.CURRENCY,
        style={"font_family": "Arial", "font_size": 18.0, "font_weight": 900, "align": "right", "nowrap": True},
    )
    whole = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Preço reais",
        text=whole_text,
        transform=Transform(x=x + currency_w, y=price_y, width=whole_w, height=price_h),
        binding_role=BindingRole.PRICE_REAIS,
        style={
            "font_family": "Arial Black",
            "font_size": max(24.0, price_h * 0.8),
            "font_weight": 900,
            "align": "right",
            "nowrap": True,
        },
    )
    cents = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Preço centavos",
        text=cents_text,
        transform=Transform(x=x + currency_w + whole_w, y=price_y, width=cents_w, height=price_h),
        binding_role=BindingRole.PRICE_CENTS,
        style={
            "font_family": "Arial",
            "font_size": max(16.0, price_h * 0.42),
            "font_weight": 900,
            "align": "left",
            "nowrap": True,
        },
    )
    unit = GraphicsNode(
        kind=NodeKind.TEXT,
        name="Unidade",
        text=unit_text,
        transform=Transform(x=x + currency_w + whole_w + cents_w, y=price_y, width=unit_w, height=price_h),
        binding_role=BindingRole.UNIT,
        style={
            "font_family": "Arial",
            "font_size": max(12.0, price_h * 0.28),
            "font_weight": 900,
            "align": "left",
            "nowrap": True,
        },
    )
    for node in (image, name, currency, whole, cents, unit):
        page.add_node(node, parent_id=group.id)
    slot = SmartSlot(
        name=f"Produto {len(page.slots) + 1}",
        page_id=page.id,
        node_by_role={
            BindingRole.IMAGE.value: image.id,
            BindingRole.NAME.value: name.id,
            BindingRole.CURRENCY.value: currency.id,
            BindingRole.PRICE_REAIS.value: whole.id,
            BindingRole.PRICE_CENTS.value: cents.id,
            BindingRole.UNIT.value: unit.id,
        },
        product_id=str(product.get("id") or card.product_id),
        metadata={"product_snapshot": product, "source": "studio-project-5x"},
    )
    page.slots[slot.id] = slot


def legacy_page_dict_to_graphics(raw: dict[str, Any]) -> GraphicsPage:
    page = GraphicsPage(
        id=str(raw.get("id") or _id("page")),
        name=str(raw.get("name") or "Página importada"),
        width=float(raw.get("width") or 794.0),
        height=float(raw.get("height") or 1123.0),
        unit=CoordinateUnit.PIXEL,
        metadata={
            "legacy_background_url": raw.get("backgroundUrl") or "",
            "legacy_source": "encartes-dom",
            "legacy_template_elements": list(raw.get("templateElements") or []),
        },
    )
    background_url = str(raw.get("backgroundUrl") or "")
    if background_url:
        page.add_node(
            GraphicsNode(
                kind=NodeKind.BACKGROUND,
                name="Design original",
                transform=Transform(x=0, y=0, width=page.width, height=page.height),
                locked=True,
                z_index=-100000,
                metadata={"source_url": background_url, "fidelity_layer": True},
            )
        )
    for raw_slot in raw.get("templateSlots") or []:
        bindings: dict[str, str] = {}
        for role_text, field_data in dict(raw_slot.get("fields") or {}).items():
            role = _legacy_role(role_text)
            if role is None:
                continue
            field = dict(field_data or {})
            kind = NodeKind.IMAGE if role is BindingRole.IMAGE else NodeKind.TEXT
            node = GraphicsNode(
                kind=kind,
                name=f"{raw_slot.get('id', 'slot')} · {role.value}",
                transform=Transform(
                    x=float(field.get("x") or 0),
                    y=float(field.get("y") or 0),
                    width=float(field.get("w") or 1),
                    height=float(field.get("h") or 1),
                ),
                binding_role=role,
                style=dict(field.get("style") or {}),
                metadata={"legacy_field": field},
            )
            page.add_node(node)
            bindings[role.value] = node.id
        slot_id = str(raw_slot.get("id") or _id("slot"))
        page.slots[slot_id] = SmartSlot(
            id=slot_id,
            name=str(raw_slot.get("id") or f"Produto {len(page.slots) + 1}"),
            page_id=page.id,
            node_by_role=bindings,
            confidence=float(raw_slot.get("confidence") or 1.0),
            metadata={"legacy_slot": dict(raw_slot)},
        )
    return page


def _legacy_role(text: str) -> BindingRole | None:
    return {
        "NOME": BindingRole.NAME,
        "IMAGEM": BindingRole.IMAGE,
        "PRECO_RS": BindingRole.CURRENCY,
        "PRECO_REAIS": BindingRole.PRICE_REAIS,
        "PRECO_CENTAVOS": BindingRole.PRICE_CENTS,
        "UNIDADE": BindingRole.UNIT,
        "LIMITE": BindingRole.LIMIT,
        "PRECO_APP": BindingRole.APP_PRICE,
    }.get(str(text))
