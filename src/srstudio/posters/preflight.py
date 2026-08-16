from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Iterable

from srstudio.core.models import Product
from srstudio.posters.auto_model import PosterAutoModelResolver
from srstudio.posters.commercial import PosterCommercialValidator
from srstudio.posters.core import PosterEngine, PosterKind


@dataclass(frozen=True, slots=True)
class PosterPreflightIssue:
    severity: str
    code: str
    product_id: str
    product: str
    message: str
    field: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class PosterPreflightReport:
    kind: PosterKind
    products: int = 0
    critical: int = 0
    warnings: int = 0
    information: int = 0
    issues: list[PosterPreflightIssue] = field(default_factory=list)
    model_summary: dict[str, int] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.products > 0 and self.critical == 0

    @property
    def total(self) -> int:
        return len(self.issues)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "products": self.products,
            "ready": self.ready,
            "critical": self.critical,
            "warnings": self.warnings,
            "information": self.information,
            "total": self.total,
            "model_summary": dict(self.model_summary),
            "issues": [issue.to_dict() for issue in self.issues],
        }


class PosterBatchPreflight:
    """Final print gate for Promotion/Wholesale batches.

    Existing commercial validation remains the source of truth for cost/sale/unit
    rules. This layer adds print-specific checks that must be evaluated across the
    whole selected batch before the final PDF can be released.
    """

    CRITICAL = "CRÍTICO"
    WARNING = "ATENÇÃO"
    INFO = "INFO"

    def __init__(self) -> None:
        self.commercial = PosterCommercialValidator()
        self.engine = PosterEngine()
        self.models = PosterAutoModelResolver()

    def evaluate(self, products: Iterable[Product], kind: PosterKind) -> PosterPreflightReport:
        items = list(products)
        report = PosterPreflightReport(kind=kind, products=len(items))
        commercial = self.commercial.evaluate_batch(items, kind)
        seen: set[tuple[str, str, str, str]] = set()

        def add(
            severity: str,
            code: str,
            product: Product,
            message: str,
            field: str = "",
        ) -> None:
            key = (severity, code, product.id, message)
            if key in seen:
                return
            seen.add(key)
            report.issues.append(
                PosterPreflightIssue(
                    severity=severity,
                    code=code,
                    product_id=product.id,
                    product=product.name or product.code or "Produto",
                    message=message,
                    field=field,
                )
            )

        for product in items:
            status = commercial.get(product.id)
            if status is not None:
                for issue in status.issues:
                    severity = self.CRITICAL if issue.severity == self.commercial.ERROR else self.WARNING
                    add(severity, issue.code, product, issue.message, issue.field)

            data = self.engine.wholesale(product) if kind == PosterKind.WHOLESALE else self.engine.promotion(product)
            poster_type = int(product.metadata.get("promotion_type", 0) or 0) if kind == PosterKind.PROMOTION else 0
            for issue in self.engine.validate(data):
                # Club-only intentionally has no secondary Club field; its main price
                # already is the exclusive Club price.
                if kind == PosterKind.PROMOTION and poster_type == 3 and issue.field == "club_price":
                    continue
                severity = {
                    "error": self.CRITICAL,
                    "warning": self.WARNING,
                    "info": self.INFO,
                }.get(str(issue.severity).lower(), self.WARNING)
                add(severity, f"DADO_{issue.field.upper()}", product, issue.message, issue.field)

            decision = self.models.decide(product, kind)
            report.model_summary[decision.short_label] = report.model_summary.get(decision.short_label, 0) + 1
            if not decision.path.is_file():
                add(
                    self.CRITICAL,
                    "MODELO_AUSENTE",
                    product,
                    f"Modelo automático não encontrado: {decision.filename}.",
                    "template",
                )

            if kind == PosterKind.PROMOTION:
                main = product.price if product.price is not None else product.retail_price
                if poster_type == 2:
                    if product.app_price is None:
                        add(
                            self.CRITICAL,
                            "CLUBE_OBRIGATORIO",
                            product,
                            "Cartaz de 2 preços está sem preço Clube/App.",
                            "app_price",
                        )
                    elif main is not None and self._same_price(main, product.app_price):
                        add(
                            self.WARNING,
                            "DOIS_PRECOS_IGUAIS",
                            product,
                            "Cartaz marcado como 2 preços possui Promoção e Clube/App iguais.",
                            "app_price",
                        )
                elif poster_type == 3 and product.price is None:
                    add(
                        self.CRITICAL,
                        "CLUBE_EXCLUSIVO_SEM_PRECO",
                        product,
                        "Clube Exclusivo está sem preço principal.",
                        "price",
                    )
                if not str(product.validity or "").strip() and poster_type != 0:
                    add(
                        self.WARNING,
                        "SEM_VALIDADE",
                        product,
                        "Cartaz promocional está sem período de validade.",
                        "validity",
                    )

            render_state = str(product.metadata.get("render_state") or "").upper().strip()
            render_error = str(product.metadata.get("render_error") or "").strip()
            if render_state == "ERRO":
                add(
                    self.CRITICAL,
                    "RENDER_ERRO",
                    product,
                    "Pré-renderização do cartaz falhou" + (f": {render_error}" if render_error else "."),
                    "render",
                )
            elif render_state in {"ALTERADO", "AGUARDANDO", "RENDERIZANDO"}:
                add(
                    self.WARNING,
                    "RENDER_PENDENTE",
                    product,
                    "Cartaz ainda está sendo atualizado; a geração final confirmará o artefato antes de liberar o PDF.",
                    "render",
                )

        report.critical = sum(issue.severity == self.CRITICAL for issue in report.issues)
        report.warnings = sum(issue.severity == self.WARNING for issue in report.issues)
        report.information = sum(issue.severity == self.INFO for issue in report.issues)
        return report

    @staticmethod
    def _same_price(left: Decimal, right: Decimal) -> bool:
        return abs(left - right) < Decimal("0.005")
