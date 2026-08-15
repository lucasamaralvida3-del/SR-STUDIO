from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from srstudio.core.models import Product
from srstudio.posters.core import PosterKind


def programmed_models_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "poster_templates" / "legacy" / "models"


@dataclass(frozen=True, slots=True)
class PosterModelDecision:
    """Deterministic model decision for one printed poster.

    The rules intentionally mirror the historical PowerPoint engine: the decision is
    made per product, so the same batch can mix one-price, two-price, Club-only and
    limit variants without user intervention.
    """

    kind: PosterKind
    filename: str
    label: str
    short_label: str
    poster_type: int
    has_limit: bool
    reason: str

    @property
    def path(self) -> Path:
        return programmed_models_root() / self.filename


class PosterAutoModelResolver:
    """Single source of truth for SR automatic print-poster model selection."""

    TYPE_ONE_PRICE = 1
    TYPE_TWO_PRICES = 2
    TYPE_CLUB_ONLY = 3
    TYPE_SALE = 0

    def decide(self, product: Product, kind: PosterKind) -> PosterModelDecision:
        if kind == PosterKind.WHOLESALE:
            return PosterModelDecision(
                kind=kind,
                filename="ATACADO.pptx",
                label="Atacado · Varejo + Atacado",
                short_label="ATACADO",
                poster_type=self.TYPE_SALE,
                has_limit=bool(str(product.cpf_limit or "").strip()),
                reason="Módulo Atacado usa o modelo ATACADO.pptx.",
            )
        return self.promotion(product)

    def promotion(self, product: Product) -> PosterModelDecision:
        poster_type, reason = self._promotion_type(product)
        has_limit = bool(str(product.cpf_limit or "").strip())

        if poster_type == self.TYPE_ONE_PRICE:
            filename = (
                "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx"
                if has_limit
                else "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx"
            )
            label = "Promoção · 1 preço" + (" · com limite" if has_limit else "")
            short = "1 PREÇO + LIMITE" if has_limit else "1 PREÇO"
        elif poster_type == self.TYPE_TWO_PRICES:
            filename = (
                "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"
                if has_limit
                else "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx"
            )
            label = "Promoção · 2 preços" + (" · com limite" if has_limit else "")
            short = "2 PREÇOS + LIMITE" if has_limit else "2 PREÇOS"
        elif poster_type == self.TYPE_CLUB_ONLY:
            filename = "CLUBE_EXCLUSIVO_COM_LIMITE.pptx" if has_limit else "CLUBE_EXCLUSIVO.pptx"
            label = "Clube Exclusivo" + (" · com limite" if has_limit else "")
            short = "CLUBE + LIMITE" if has_limit else "CLUBE EXCLUSIVO"
        else:
            filename = "CARTAZ_VENDA.pptx"
            label = "Cartaz Venda"
            short = "CARTAZ VENDA"

        return PosterModelDecision(
            kind=PosterKind.PROMOTION,
            filename=filename,
            label=label,
            short_label=short,
            poster_type=poster_type,
            has_limit=has_limit,
            reason=reason,
        )

    def summarize(self, products: list[Product], kind: PosterKind) -> dict[str, int]:
        counts: dict[str, int] = {}
        for product in products:
            decision = self.decide(product, kind)
            counts[decision.short_label] = counts.get(decision.short_label, 0) + 1
        return counts

    @classmethod
    def _promotion_type(cls, product: Product) -> tuple[int, str]:
        raw_type = product.metadata.get("promotion_type")
        try:
            stored = int(raw_type) if raw_type is not None and str(raw_type).strip() else None
        except (TypeError, ValueError):
            stored = None

        if stored in {cls.TYPE_ONE_PRICE, cls.TYPE_TWO_PRICES, cls.TYPE_CLUB_ONLY, cls.TYPE_SALE}:
            reasons = {
                cls.TYPE_ONE_PRICE: "Planilha: preço PROMOÇÃO sem Clube diferente.",
                cls.TYPE_TWO_PRICES: "Planilha: PROMOÇÃO e CLUBE possuem preços diferentes.",
                cls.TYPE_CLUB_ONLY: "Planilha: somente preço CLUBE informado.",
                cls.TYPE_SALE: "Item marcado como Cartaz Venda.",
            }
            return stored, reasons[stored]

        # Compatibility for products coming from older projects or generic imports.
        if bool(product.metadata.get("sale_poster") or product.metadata.get("cartaz_venda")):
            return cls.TYPE_SALE, "Item marcado como Cartaz Venda."
        if product.app_price is not None and product.price is not None and product.app_price != product.price:
            return cls.TYPE_TWO_PRICES, "Inferido: preço principal e Clube são diferentes."
        if product.app_price is not None and product.price is None:
            return cls.TYPE_CLUB_ONLY, "Inferido: existe apenas preço Clube."
        return cls.TYPE_ONE_PRICE, "Inferido: existe somente um preço comercial para o cartaz."
