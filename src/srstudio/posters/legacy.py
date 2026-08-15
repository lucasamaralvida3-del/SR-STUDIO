from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from srstudio.core.models import Product, to_decimal
from srstudio.posters.core import PosterData, PosterEngine, PosterIssue, PosterKind, PrintPosterService


class SRPosterData(PosterData):
    """Poster payload compatible with the proven Stable cartaz engines."""

    def fields(self) -> dict[str, str]:
        values = super().fields()
        values.update(
            {
                "nome": self.name,
                "produto": self.name,
                "promocao": self._money(self.main_price),
                "clube": self._money(self.club_price),
                "varejo": self._money(self.retail_price),
                "atacado": self._money(self.wholesale_price),
                "quantidade": self.quantity,
                "unidade": self.unit,
                "total": self.wholesale_total(),
                "quantidade_texto": self.quantity_text(short=True),
                "quantidade_2_texto": self.quantity_text(short=False),
                "validade": self.validity,
                "limite": self._limit_text(),
                "enunciado": self._campaign_text(),
            }
        )
        return values

    def wholesale_total(self) -> str:
        quantity = self._quantity_decimal()
        wholesale = to_decimal(self.wholesale_price)
        if quantity is None or wholesale is None:
            return ""
        total = (quantity * wholesale).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return self._money(total)

    def quantity_text(self, *, short: bool) -> str:
        quantity = str(self.quantity or "").strip()
        if not quantity:
            return ""
        unit = (self.unit or "UN").upper().strip()
        if unit == "KG":
            if short:
                return f"{quantity} KG SAI A:"
            return f"NA COMPRA A PARTIR DE {quantity} KG O KG SAI POR APENAS:"
        if unit in {"À LATA", "A LATA"}:
            if short:
                return f"{quantity} LATAS SAEM A:"
            return f"NA COMPRA A PARTIR DE {quantity} LATAS, O PREÇO À LATA SAI POR APENAS:"
        if unit in {"À GARRAFA", "A GARRAFA"}:
            if short:
                return f"{quantity} GARRAFAS SAEM A:"
            return f"NA COMPRA A PARTIR DE {quantity} GARRAFAS, O PREÇO À GARRAFA SAI POR APENAS:"
        if short:
            return f"{quantity} UN SAI A:"
        return f"NA COMPRA A PARTIR DE {quantity} A UNIDADE SAI POR APENAS:"

    def _quantity_decimal(self) -> Decimal | None:
        raw = str(self.quantity or "").strip()
        if not raw:
            return None
        return to_decimal(raw)

    @staticmethod
    def _money(value) -> str:
        amount = to_decimal(value)
        if amount is None:
            return ""
        return f"{amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}".replace(".", ",")


class SRPosterEngine(PosterEngine):
    """v5 commercial engine that preserves the Stable promotion/wholesale payload."""

    @staticmethod
    def unit_label(product: Product) -> str:
        unit = (product.unit or "UN").upper().strip()
        if unit == "KG":
            return "O KG"
        if unit in {"À LATA", "A LATA"}:
            return "A LATA"
        if unit in {"À GARRAFA", "A GARRAFA"}:
            return "A GARRAFA"
        return PosterEngine.unit_label(product)

    def promotion(self, product: Product, campaign: str = "") -> SRPosterData:
        base = super().promotion(product, campaign)
        poster_type = int(product.metadata.get("promotion_type", 0) or 0)
        campaign_value = base.campaign
        main_price = base.main_price
        club_price = base.club_price
        if poster_type == 3:
            campaign_value = "CLUBE EXCLUSIVO"
            main_price = None
            club_price = product.price
        return SRPosterData(
            kind=PosterKind.PROMOTION,
            product_id=base.product_id,
            name=base.name,
            campaign=campaign_value,
            unit=base.unit,
            unit_label=base.unit_label,
            limit=base.limit,
            validity=base.validity,
            quantity=base.quantity,
            image_path=base.image_path,
            main_price=main_price,
            club_price=club_price,
            retail_price=base.retail_price,
            wholesale_price=base.wholesale_price,
        )

    def wholesale(self, product: Product, campaign: str = "Atacado") -> SRPosterData:
        base = super().wholesale(product, campaign)
        return SRPosterData(
            kind=PosterKind.WHOLESALE,
            product_id=base.product_id,
            name=base.name,
            campaign=base.campaign,
            unit=product.unit,
            unit_label=base.unit_label,
            limit=base.limit,
            validity=base.validity,
            quantity=base.quantity,
            image_path=base.image_path,
            main_price=base.main_price,
            club_price=base.club_price,
            retail_price=base.retail_price,
            wholesale_price=base.wholesale_price,
        )

    def validate(self, data: PosterData) -> list[PosterIssue]:
        if data.kind == PosterKind.PROMOTION and data.campaign.upper().startswith("CLUBE EXCLUSIVO"):
            issues: list[PosterIssue] = []
            if not data.name.strip():
                issues.append(PosterIssue("error", "name", "Produto sem nome."))
            if data.club_price is None:
                issues.append(PosterIssue("error", "club_price", "Produto sem preço Clube Exclusivo."))
            return issues
        return super().validate(data)


class SRPrintPosterService(PrintPosterService):
    def __init__(self) -> None:
        super().__init__()
        self.engine = SRPosterEngine()
