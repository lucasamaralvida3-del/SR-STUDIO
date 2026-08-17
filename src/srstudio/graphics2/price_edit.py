from __future__ import annotations

"""Atomic PriceBlock editing for the G2 flyer editor."""

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from .model import NodeKind
from .semantic_blocks import semantic_block

if TYPE_CHECKING:
    from .operations import GraphicsSession


def _parse_price(value: object) -> tuple[str, str, str]:
    text = str(value or "").strip().replace("R$", "").replace(" ", "")
    if not text:
        raise ValueError("Preço vazio.")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Preço inválido: {value}") from exc
    if amount < 0:
        raise ValueError("Preço não pode ser negativo.")
    whole, cents = f"{amount:.2f}".split(".")
    cents_text = f",{cents}"
    return whole, cents_text, f"{whole}{cents_text}"


def _unit_text(unit: object, template: str) -> str:
    cleaned = str(unit or "").upper().strip().lstrip("/")
    if not cleaned:
        return ""
    prefix = "/" if "/" in str(template or "") else ""
    return f"{prefix}{cleaned}"


def edit_price_block(
    session: "GraphicsSession",
    block_id: str,
    price: object,
    *,
    unit: object | None = None,
    currency: str = "R$",
) -> bool:
    """Edit a semantic PriceBlock without changing template geometry.

    Split-price layouts (currency/reais/cents/unit) and complete price labels are
    updated together in one history transaction. The Smart Slot product snapshot
    is kept coherent so save/open and later product operations do not resurrect
    stale values.
    """

    block = semantic_block(session.page, str(block_id))
    if not block or str(block.get("kind") or "") != "price_block":
        return False

    roles = dict(block.get("roles") or {})
    member_ids = [str(node_id) for node_id in block.get("members") or []]
    members = [session.page.node(node_id) for node_id in member_ids]
    members = [node for node in members if node is not None]
    if not members or any(session.effective_locked(node.id) for node in members):
        return False

    whole, cents, complete = _parse_price(price)
    currency_text = str(currency or "R$").strip() or "R$"
    role_values = {
        "currency": currency_text,
        "reais": whole,
        "cents": cents,
        "complete": f"{currency_text} {complete}".strip(),
    }

    with session.transaction("Editar bloco de preço"):
        for role, value in role_values.items():
            for node_id in roles.get(role) or []:
                node = session.page.node(str(node_id))
                if node is not None and node.kind is NodeKind.TEXT:
                    node.text = value
                    node.visible = bool(value)

        if unit is not None:
            for node_id in roles.get("unit") or []:
                node = session.page.node(str(node_id))
                if node is None or node.kind is not NodeKind.TEXT:
                    continue
                node.text = _unit_text(unit, node.text)
                node.visible = bool(node.text)

        slot_id = str(block.get("slot_id") or "")
        slot = session.page.slots.get(slot_id)
        if slot is not None:
            snapshot = dict(slot.metadata.get("product_snapshot") or {})
            price_key = "app_price" if "app-price" in str(block_id) else "price"
            snapshot[price_key] = complete
            if unit is not None:
                snapshot["unit"] = str(unit or "").upper().strip().lstrip("/")
            slot.metadata["product_snapshot"] = snapshot

    return True
