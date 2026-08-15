from __future__ import annotations

from copy import deepcopy
from typing import Any

from srstudio.core.models import Page, Product, ProductCard
from srstudio.editor.history import LambdaCommand
from srstudio.pricing.engine import PriceEngine


class DetectedSlotService:
    """Bind products to semantic Canva slots while preserving the original artwork."""

    PRIMARY_ROLES = {
        "price_complete",
        "price_currency",
        "price_integer",
        "price_cents",
        "unit",
    }
    SECONDARY_ROLES = {
        "app_price_complete",
        "app_price_currency",
        "app_price_integer",
        "app_price_cents",
        "app_unit",
    }

    @staticmethod
    def is_detected(card: ProductCard) -> bool:
        return bool(card.overrides.get("slot_detected", False))

    @classmethod
    def slots(cls, page: Page) -> list[ProductCard]:
        return sorted(
            (card for card in page.cards if cls.is_detected(card)),
            key=lambda card: (round(card.y, 3), round(card.x, 3), card.z_index),
        )

    @classmethod
    def has_slots(cls, page: Page) -> bool:
        return any(cls.is_detected(card) for card in page.cards)

    @classmethod
    def next_empty(cls, page: Page) -> ProductCard | None:
        return next(
            (
                card
                for card in cls.slots(page)
                if not bool(card.overrides.get("slot_filled", False))
            ),
            None,
        )

    @staticmethod
    def bound_elements(page: Page, card_id: str) -> list[dict[str, Any]]:
        return [element for element in page.elements if str(element.get("slot_id") or "") == card_id]

    @classmethod
    def can_fill(cls, page: Page, card: ProductCard) -> bool:
        return cls.is_detected(card) and bool(cls.bound_elements(page, card.id))

    @classmethod
    def fill_with_history(cls, controller, card: ProductCard, product: Product) -> bool:
        page = controller.page
        if not cls.can_fill(page, card):
            return False

        if controller.project.product_by_id(product.id) is None:
            controller.project.products.append(product)

        before_product_id = card.product_id
        before_overrides = deepcopy(card.overrides)
        bound = cls.bound_elements(page, card.id)
        before_elements = [deepcopy(element) for element in bound]

        def do() -> None:
            cls.apply_product(page, card, product)
            controller.scene.selection.ids = {card.id}

        def undo() -> None:
            card.product_id = before_product_id
            card.overrides.clear()
            card.overrides.update(deepcopy(before_overrides))
            current = cls.bound_elements(page, card.id)
            for element, previous in zip(current, before_elements, strict=False):
                element.clear()
                element.update(deepcopy(previous))
            controller.scene.selection.ids = {card.id}

        controller.history.execute(LambdaCommand("Preencher slot detectado", do, undo))
        return True

    @classmethod
    def clear_with_history(cls, controller, card: ProductCard) -> bool:
        page = controller.page
        if not cls.can_fill(page, card):
            return False

        before_product_id = card.product_id
        before_overrides = deepcopy(card.overrides)
        bound = cls.bound_elements(page, card.id)
        before_elements = [deepcopy(element) for element in bound]
        template_product_id = str(card.overrides.get("slot_template_product_id") or before_product_id)

        def do() -> None:
            cls.restore_template(page, card)
            card.product_id = template_product_id
            controller.scene.selection.ids = {card.id}

        def undo() -> None:
            card.product_id = before_product_id
            card.overrides.clear()
            card.overrides.update(deepcopy(before_overrides))
            current = cls.bound_elements(page, card.id)
            for element, previous in zip(current, before_elements, strict=False):
                element.clear()
                element.update(deepcopy(previous))
            controller.scene.selection.ids = {card.id}

        controller.history.execute(LambdaCommand("Limpar slot detectado", do, undo))
        return True

    @classmethod
    def apply_product(cls, page: Page, card: ProductCard, product: Product) -> None:
        engine = PriceEngine()
        primary = engine.split(product.price, product.unit)
        secondary = engine.split(product.app_price, product.unit)

        for element in cls.bound_elements(page, card.id):
            role = str(element.get("slot_role") or "")
            if role == "name":
                element["text"] = product.name
                element["hidden"] = False
            elif role == "image":
                element["path"] = product.image_path if product.has_image else ""
                element["hidden"] = False
            elif role in cls.PRIMARY_ROLES:
                cls._apply_price_role(element, role, primary, product.unit)
            elif role in cls.SECONDARY_ROLES:
                if secondary.raw is None:
                    element["hidden"] = True
                else:
                    normalized = role.removeprefix("app_")
                    cls._apply_price_role(element, normalized, secondary, product.unit)

        card.product_id = product.id
        card.overrides["slot_filled"] = True
        card.overrides["slot_product_id"] = product.id
        card.overrides["hidden"] = True

    @classmethod
    def restore_template(cls, page: Page, card: ProductCard) -> None:
        for element in cls.bound_elements(page, card.id):
            if "template_text" in element:
                element["text"] = element.get("template_text", "")
            if "template_path" in element:
                element["path"] = element.get("template_path", "")
            element["hidden"] = bool(element.get("template_hidden", False))
        card.overrides["slot_filled"] = False
        card.overrides.pop("slot_product_id", None)
        card.overrides["hidden"] = True

    @staticmethod
    def _apply_price_role(element: dict[str, Any], role: str, parts, unit: str) -> None:
        element["hidden"] = False
        if role == "price_complete":
            template = str(element.get("template_text") or element.get("text") or "")
            suffix = f"/{parts.unit}" if "/" in template and parts.unit else ""
            element["text"] = f"{parts.currency} {parts.integer},{parts.cents}{suffix}" if parts.integer else ""
        elif role == "price_currency":
            element["text"] = parts.currency if parts.integer else ""
        elif role == "price_integer":
            element["text"] = parts.integer
        elif role == "price_cents":
            template = str(element.get("template_text") or element.get("text") or "")
            prefix = "," if template.strip().startswith(",") else ("." if template.strip().startswith(".") else ",")
            element["text"] = f"{prefix}{parts.cents}" if parts.integer else ""
        elif role == "unit":
            template = str(element.get("template_text") or element.get("text") or "").strip()
            final_unit = (unit or parts.unit or "UN").upper().strip()
            if template.startswith("/"):
                element["text"] = f"/{final_unit}"
            else:
                element["text"] = final_unit
