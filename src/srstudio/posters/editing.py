from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from time import time

from srstudio.core.models import Product, to_decimal
from srstudio.posters.core import PosterKind


@dataclass(frozen=True, slots=True)
class PosterEditResult:
    changed: bool
    field: str
    message: str = ""


class PosterProductEditor:
    """Deterministic edits for the poster grid; UI only supplies strings."""

    EDITABLE_PROMOTION = {"name", "price1", "price2", "unit", "limit"}
    EDITABLE_WHOLESALE = {"name", "price1", "price2", "quantity", "unit", "limit"}
    UNIT_ALIASES = {
        "UN": "UN",
        "UND": "UN",
        "UNIDADE": "UN",
        "KG": "KG",
        "QUILO": "KG",
        "A LATA": "À LATA",
        "À LATA": "À LATA",
        "LATA": "À LATA",
        "A GARRAFA": "À GARRAFA",
        "À GARRAFA": "À GARRAFA",
        "GARRAFA": "À GARRAFA",
    }

    def editable(self, kind: PosterKind) -> set[str]:
        return set(self.EDITABLE_WHOLESALE if kind == PosterKind.WHOLESALE else self.EDITABLE_PROMOTION)

    def raw_value(self, product: Product, kind: PosterKind, field: str) -> str:
        if field == "name":
            return product.name
        if field == "unit":
            return product.unit
        if field == "limit":
            return product.cpf_limit
        if field == "quantity":
            return product.quantity
        if field == "price1":
            value = product.retail_price if kind == PosterKind.WHOLESALE else product.price
            return self.decimal_text(value)
        if field == "price2":
            value = product.wholesale_price if kind == PosterKind.WHOLESALE else product.app_price
            if kind == PosterKind.PROMOTION and value is None and int(product.metadata.get("promotion_type", 0) or 0) == 3:
                value = product.price
            return self.decimal_text(value)
        return ""

    def apply(self, product: Product, kind: PosterKind, field: str, raw_value: str) -> PosterEditResult:
        if field not in self.editable(kind):
            return PosterEditResult(False, field, "Campo somente leitura.")
        before = self._signature(product)
        before_value = self.raw_value(product, kind, field)
        text = str(raw_value or "").strip()

        if field == "name":
            cleaned = " ".join(text.split()).upper()
            if not cleaned:
                return PosterEditResult(False, field, "O nome do produto não pode ficar vazio.")
            product.display_name = cleaned
        elif field == "unit":
            normalized = self.UNIT_ALIASES.get(text.upper())
            if normalized is None:
                return PosterEditResult(False, field, "Unidade válida: UN, KG, À LATA ou À GARRAFA.")
            product.unit = normalized
        elif field == "limit":
            product.cpf_limit = text.upper()
        elif field == "quantity":
            product.quantity = text.upper()
        elif field in {"price1", "price2"}:
            value = None if not text else to_decimal(text)
            if text and value is None:
                return PosterEditResult(False, field, "Preço inválido. Use por exemplo 4,29.")
            if kind == PosterKind.WHOLESALE:
                if field == "price1":
                    product.retail_price = value
                    product.price = value
                else:
                    product.wholesale_price = value
            else:
                self._apply_promotion_price(product, field, value)

        changed = before != self._signature(product)
        if changed:
            product.metadata["edited"] = True
            fields = product.metadata.setdefault("edited_fields", [])
            if field not in fields:
                fields.append(field)
            self.record_history(
                product,
                field,
                before_value,
                self.raw_value(product, kind, field),
                source="manual",
            )
        return PosterEditResult(changed, field, "Alteração aplicada." if changed else "Sem alteração.")

    @staticmethod
    def record_history(
        product: Product,
        field: str,
        before: object,
        after: object,
        *,
        source: str = "manual",
    ) -> None:
        """Keep a compact audit trail and coalesce rapid typing in the same field."""

        now_epoch = time()
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        history = product.metadata.setdefault("edit_history", [])
        if not isinstance(history, list):
            history = []
            product.metadata["edit_history"] = history
        before_text = str(before or "")
        after_text = str(after or "")
        if history:
            last = history[-1]
            if (
                isinstance(last, dict)
                and str(last.get("field") or "") == field
                and str(last.get("source") or "manual") == source
                and before_text == str(last.get("after") or "")
                and now_epoch - float(last.get("_ts") or 0) <= 5.0
            ):
                last["after"] = after_text
                last["at"] = now_iso
                last["_ts"] = now_epoch
                return
        history.append(
            {
                "field": field,
                "before": before_text,
                "after": after_text,
                "source": source,
                "at": now_iso,
                "_ts": now_epoch,
            }
        )
        if len(history) > 100:
            del history[:-100]

    @staticmethod
    def _apply_promotion_price(product: Product, field: str, value: Decimal | None) -> None:
        if field == "price1":
            if value is None:
                if product.app_price is not None:
                    product.price = product.app_price
                    product.app_price = None
                    product.metadata["promotion_type"] = 3
                else:
                    product.price = None
                    product.metadata["promotion_type"] = 1
                return
            product.price = value
            if product.app_price is not None and abs(product.app_price - value) >= Decimal("0.005"):
                product.metadata["promotion_type"] = 2
            else:
                if product.app_price is not None and abs(product.app_price - value) < Decimal("0.005"):
                    product.app_price = None
                product.metadata["promotion_type"] = 1
            return

        if value is None:
            product.app_price = None
            product.metadata["promotion_type"] = 1
            return
        if product.price is None:
            product.price = value
            product.app_price = None
            product.metadata["promotion_type"] = 3
            return
        if abs(product.price - value) < Decimal("0.005"):
            product.app_price = None
            product.metadata["promotion_type"] = 1
            return
        product.app_price = value
        product.metadata["promotion_type"] = 2

    @staticmethod
    def decimal_text(value: Decimal | None) -> str:
        return "" if value is None else f"{value:.2f}".replace(".", ",")

    @staticmethod
    def _signature(product: Product) -> tuple:
        return (
            product.display_name,
            product.price,
            product.app_price,
            product.retail_price,
            product.wholesale_price,
            product.unit,
            product.quantity,
            product.cpf_limit,
            product.metadata.get("promotion_type"),
        )
