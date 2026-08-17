from __future__ import annotations

"""Gate de usabilidade específico do Studio de Encartes / Graphics2.

Este módulo NÃO substitui o Production Gate nem os Golden Masters. Ele mede se
um documento real possui estrutura suficiente para atravessar o fluxo humano do
editor: página visível, conteúdo editável, semântica de produto/preço e
persistência estrutural segura.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .model import GraphicsDocument, NodeKind
from .preflight import run_preflight


Severity = Literal["blocker", "warning", "info"]


@dataclass(slots=True, frozen=True)
class UsabilityCheck:
    code: str
    passed: bool
    severity: Severity
    message: str


@dataclass(slots=True)
class EncarteUsabilityReport:
    ready: bool
    checks: list[UsabilityCheck] = field(default_factory=list)
    metrics: dict[str, int | float | bool] = field(default_factory=dict)

    @property
    def blockers(self) -> int:
        return sum(not item.passed and item.severity == "blocker" for item in self.checks)

    @property
    def warnings(self) -> int:
        return sum(not item.passed and item.severity == "warning" for item in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "checks": [asdict(item) for item in self.checks],
            "metrics": dict(self.metrics),
        }


def inspect_encarte_usability(
    document: GraphicsDocument,
    *,
    require_semantic_products: bool = True,
    require_bound_product: bool = False,
) -> EncarteUsabilityReport:
    """Avalia um `.srscene` como encarte editável, sem alterar o documento.

    `require_semantic_products=True` representa o fluxo real desejado do Studio:
    ProductCard + PriceBlock recuperados ou declarados. Pode ser desligado para
    diagnosticar layouts ainda puramente gráficos durante a migração.
    """

    checks: list[UsabilityCheck] = []
    preflight = run_preflight(document)
    preflight_errors = sum(issue.severity == "error" for issue in preflight)
    preflight_warnings = sum(issue.severity == "warning" for issue in preflight)
    _check(
        checks,
        "STRUCTURAL_INTEGRITY",
        preflight_errors == 0,
        "blocker",
        "Documento estruturalmente íntegro." if preflight_errors == 0 else f"Preflight possui {preflight_errors} erro(s).",
    )

    page_ids = [page.id for page in document.pages]
    duplicate_page_ids = len(page_ids) - len(set(page_ids))
    _check(
        checks,
        "UNIQUE_PAGE_IDS",
        duplicate_page_ids == 0,
        "blocker",
        "IDs de página são únicos." if duplicate_page_ids == 0 else f"Há {duplicate_page_ids} página(s) com ID duplicado.",
    )

    active_page_valid = document.page(document.active_page_id) is not None
    _check(
        checks,
        "ACTIVE_PAGE_VALID",
        active_page_valid,
        "blocker",
        "Página ativa é válida." if active_page_valid else "active_page_id não aponta para uma página existente.",
    )

    visible_nodes = 0
    text_nodes = 0
    image_nodes = 0
    editable_nodes = 0
    semantic_blocks = 0
    product_cards = 0
    price_blocks = 0
    semantic_missing_members = 0
    slots = 0
    bound_slots = 0
    slot_page_mismatches = 0

    for page in document.pages:
        visible_nodes += sum(node.visible for node in page.nodes.values())
        text_nodes += sum(node.kind is NodeKind.TEXT for node in page.nodes.values())
        image_nodes += sum(node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND} for node in page.nodes.values())
        editable_nodes += sum(node.visible and not node.locked for node in page.nodes.values())
        slots += len(page.slots)
        bound_slots += sum(bool(slot.product_id) for slot in page.slots.values())
        slot_page_mismatches += sum(bool(slot.page_id) and slot.page_id != page.id for slot in page.slots.values())

        raw_blocks = page.metadata.get("semantic_blocks")
        if isinstance(raw_blocks, dict):
            semantic_blocks += len(raw_blocks)
            for block in raw_blocks.values():
                if not isinstance(block, dict):
                    continue
                kind = str(block.get("kind") or "")
                if kind == "product_card":
                    product_cards += 1
                elif kind == "price_block":
                    price_blocks += 1
                for member_id in block.get("members") or []:
                    if str(member_id) not in page.nodes:
                        semantic_missing_members += 1

    _check(
        checks,
        "VISIBLE_CONTENT",
        visible_nodes > 0,
        "blocker",
        "O encarte possui conteúdo visível." if visible_nodes else "Nenhum conteúdo visível foi encontrado.",
    )
    _check(
        checks,
        "EDITABLE_CONTENT",
        editable_nodes > 0,
        "blocker",
        "Há conteúdo editável no canvas." if editable_nodes else "Todo o conteúdo está bloqueado ou invisível.",
    )
    _check(
        checks,
        "TEXT_CONTENT",
        text_nodes > 0,
        "warning",
        "Há textos editáveis/importados." if text_nodes else "Nenhum texto foi encontrado no encarte.",
    )
    _check(
        checks,
        "IMAGE_CONTENT",
        image_nodes > 0,
        "warning",
        "Há imagens/backgrounds no encarte." if image_nodes else "Nenhuma imagem/background foi encontrada.",
    )
    _check(
        checks,
        "SLOT_PAGE_OWNERSHIP",
        slot_page_mismatches == 0,
        "blocker",
        "SmartSlots pertencem às páginas corretas." if slot_page_mismatches == 0 else f"Há {slot_page_mismatches} SmartSlot(s) ligados à página errada.",
    )
    _check(
        checks,
        "SEMANTIC_MEMBER_INTEGRITY",
        semantic_missing_members == 0,
        "blocker",
        "Blocos semânticos apontam apenas para nodes existentes." if semantic_missing_members == 0 else f"Há {semantic_missing_members} referência(s) semântica(s) órfã(s).",
    )

    if require_semantic_products:
        _check(
            checks,
            "PRODUCT_CARD_AVAILABLE",
            product_cards > 0,
            "blocker",
            f"{product_cards} ProductCard(s) disponível(is)." if product_cards else "Nenhum ProductCard foi recuperado/declarado.",
        )
        _check(
            checks,
            "PRICE_BLOCK_AVAILABLE",
            price_blocks > 0,
            "blocker",
            f"{price_blocks} PriceBlock(s) disponível(is)." if price_blocks else "Nenhum PriceBlock foi recuperado/declarado.",
        )
        _check(
            checks,
            "SMART_SLOT_AVAILABLE",
            slots > 0,
            "blocker",
            f"{slots} SmartSlot(s) disponível(is)." if slots else "Nenhum SmartSlot está disponível para receber produtos.",
        )

    if require_bound_product:
        _check(
            checks,
            "BOUND_PRODUCT_AVAILABLE",
            bound_slots > 0,
            "blocker",
            f"{bound_slots} slot(s) contém produto vinculado." if bound_slots else "Nenhum produto foi vinculado a um SmartSlot.",
        )

    metrics: dict[str, int | float | bool] = {
        "pages": len(document.pages),
        "visible_nodes": visible_nodes,
        "editable_nodes": editable_nodes,
        "text_nodes": text_nodes,
        "image_nodes": image_nodes,
        "smart_slots": slots,
        "bound_slots": bound_slots,
        "semantic_blocks": semantic_blocks,
        "product_cards": product_cards,
        "price_blocks": price_blocks,
        "semantic_missing_members": semantic_missing_members,
        "slot_page_mismatches": slot_page_mismatches,
        "preflight_errors": preflight_errors,
        "preflight_warnings": preflight_warnings,
        "duplicate_page_ids": duplicate_page_ids,
        "active_page_valid": active_page_valid,
    }
    blockers = sum(not item.passed and item.severity == "blocker" for item in checks)
    return EncarteUsabilityReport(ready=blockers == 0, checks=checks, metrics=metrics)


def _check(checks: list[UsabilityCheck], code: str, passed: bool, severity: Severity, message: str) -> None:
    checks.append(UsabilityCheck(code=code, passed=bool(passed), severity=severity, message=message))
