from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from srstudio.core.models import to_decimal


@dataclass(frozen=True, slots=True)
class PriceParts:
    currency: str
    integer: str
    cents: str
    unit: str
    raw: Decimal | None

    @property
    def formatted(self) -> str:
        if self.raw is None:
            return ""
        suffix = f"/{self.unit}" if self.unit else ""
        return f"{self.currency} {self.integer},{self.cents}{suffix}".strip()


class PriceEngine:
    """Single source of truth for every price displayed by SR Studio."""

    def __init__(self, currency: str = "R$", default_unit: str = "UN") -> None:
        self.currency = currency
        self.default_unit = default_unit

    def split(self, value: Any, unit: str | None = None) -> PriceParts:
        amount = to_decimal(value)
        final_unit = (unit or self.default_unit or "").upper().strip()
        if amount is None:
            return PriceParts(self.currency, "", "", final_unit, None)
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        integer, cents = f"{amount:.2f}".split(".")
        return PriceParts(self.currency, integer, cents, final_unit, amount)

    def compare(self, current: Any, reference: Any) -> dict[str, Any]:
        cur = to_decimal(current)
        ref = to_decimal(reference)
        if cur is None or ref in (None, Decimal("0")):
            return {"available": False, "difference": None, "percent": None}
        difference = cur - ref
        percent = (difference / ref * Decimal("100")).quantize(Decimal("0.1"))
        return {"available": True, "difference": difference, "percent": percent}

    def promotional_model(
        self,
        *,
        regular: Any = None,
        promo: Any = None,
        app: Any = None,
        wholesale: Any = None,
        unit: str = "UN",
        cpf_limit: str = "",
    ) -> dict[str, Any]:
        return {
            "regular": self.split(regular, unit),
            "promo": self.split(promo, unit),
            "app": self.split(app, unit),
            "wholesale": self.split(wholesale, unit),
            "cpf_limit": cpf_limit.strip(),
        }
