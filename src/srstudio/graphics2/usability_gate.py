from __future__ import annotations

"""Editor-readiness diagnostics for the SR Graphics Engine 2 flyer workflow.

This gate is intentionally independent from the visual Golden Master /
Production Gate. It answers a different question: is the current SR Scene
structurally safe enough to perform the day-to-day flyer editing workflow?
It never relaxes visual thresholds and never writes to the document.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .model import GraphicsDocument, NodeKind


@dataclass(slots=True, frozen=True)
class UsabilityIssue:
    severity: Literal["blocker", "warning", "info"]
    code: str
    message: str
    page_id: str = ""
    object_id: str = ""


@dataclass(slots=True)
class G2UsabilityReport:
    professional_usable: bool
    page_count: int
    populated_pages: int
    node_count: int
    visible_nodes: int
    editable_text_nodes: int
    image_nodes: int
    smart_slots: int
    bound_slots: int
    product_cards: int
    price_blocks: int
    issues: list[UsabilityIssue] = field(default_factory=list)

    @property
    def blockers(self) -> int:
        return sum(issue.severity == "blocker" for issue in self.issues)

    @property
    def warnings(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = self.blockers
        payload["warnings"] = self.warnings
        return payload


def inspect_g2_usability(
    document: GraphicsDocument,
    *,
    require_multi_product_page: bool = False,
) -> G2UsabilityReport:
    """Inspect scene safety and flyer-editing readiness without mutating it."""

    issues: list[UsabilityIssue] = []
    page_count = len(document.pages)
    populated_pages = 0
    node_count = 0
    visible_nodes = 0
    editable_text_nodes = 0
    image_nodes = 0
    smart_slots = 0
    bound_slots = 0
    product_cards = 0
    price_blocks = 0

    if not document.pages:
        issues.append(UsabilityIssue("blocker", "NO_PAGES", "O projeto não possui páginas."))

    page_ids: set[str] = set()
    global_node_ids: set[str] = set()
    global_slot_ids: set[str] = set()
    multiproduct_found = False

    for page in document.pages:
        if not page.id:
            issues.append(UsabilityIssue("blocker", "EMPTY_PAGE_ID", "Página sem id canônico."))
        elif page.id in page_ids:
            issues.append(
                UsabilityIssue("blocker", "DUPLICATE_PAGE_ID", "Duas páginas compartilham o mesmo id.", page.id)
            )
        page_ids.add(page.id)

        if page.width <= 0 or page.height <= 0:
            issues.append(
                UsabilityIssue("blocker", "INVALID_PAGE_SIZE", "Página possui dimensões inválidas.", page.id)
            )

        page_visible = [node for node in page.nodes.values() if node.visible]
        if page_visible:
            populated_pages += 1
        node_count += len(page.nodes)
        visible_nodes += len(page_visible)
        editable_text_nodes += sum(
            node.visible and not node.locked and node.kind is NodeKind.TEXT
            for node in page.nodes.values()
        )
        image_nodes += sum(
            node.visible and node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}
            for node in page.nodes.values()
        )

        if page.nodes and not page.roots:
            issues.append(
                UsabilityIssue("warning", "PAGE_WITHOUT_ROOTS", "Página possui nodes, mas nenhuma raiz.", page.id)
            )

        for root_id in page.roots:
            if root_id not in page.nodes:
                issues.append(
                    UsabilityIssue(
                        "blocker",
                        "DANGLING_ROOT",
                        "Raiz aponta para node inexistente.",
                        page.id,
                        root_id,
                    )
                )

        for node_id, node in page.nodes.items():
            if node_id != node.id:
                issues.append(
                    UsabilityIssue(
                        "blocker",
                        "NODE_KEY_ID_MISMATCH",
                        "Chave do node diverge do id armazenado.",
                        page.id,
                        node_id,
                    )
                )
            if node_id in global_node_ids:
                issues.append(
                    UsabilityIssue(
                        "blocker",
                        "DUPLICATE_NODE_ID_ACROSS_PAGES",
                        "Node id é reutilizado em mais de uma página.",
                        page.id,
                        node_id,
                    )
                )
            global_node_ids.add(node_id)

            if node.parent_id and node.parent_id not in page.nodes:
                issues.append(
                    UsabilityIssue(
                        "blocker",
                        "DANGLING_PARENT",
                        "Node aponta para pai inexistente.",
                        page.id,
                        node_id,
                    )
                )
            for child_id in node.children:
                child = page.nodes.get(child_id)
                if child is None:
                    issues.append(
                        UsabilityIssue(
                            "blocker",
                            "DANGLING_CHILD",
                            "Grupo aponta para filho inexistente.",
                            page.id,
                            child_id,
                        )
                    )
                elif child.parent_id != node_id:
                    issues.append(
                        UsabilityIssue(
                            "blocker",
                            "PARENT_CHILD_MISMATCH",
                            "Relação pai/filho não é recíproca.",
                            page.id,
                            child_id,
                        )
                    )

        page_bound_slots = 0
        for slot_id, slot in page.slots.items():
            smart_slots += 1
            if slot_id != slot.id:
                issues.append(
                    UsabilityIssue(
                        "blocker",
                        "SLOT_KEY_ID_MISMATCH",
                        "Chave do Smart Slot diverge do id armazenado.",
                        page.id,
                        slot_id,
                    )
                )
            if slot_id in global_slot_ids:
                issues.append(
                    UsabilityIssue(
                        "blocker",
                        "DUPLICATE_SLOT_ID_ACROSS_PAGES",
                        "Smart Slot id é reutilizado em mais de uma página.",
                        page.id,
                        slot_id,
                    )
                )
            global_slot_ids.add(slot_id)

            if slot.page_id != page.id:
                issues.append(
                    UsabilityIssue(
                        "blocker",
                        "SLOT_PAGE_MISMATCH",
                        "Smart Slot aponta para outra página.",
                        page.id,
                        slot_id,
                    )
                )
            for role, node_id in slot.node_by_role.items():
                if node_id not in page.nodes:
                    issues.append(
                        UsabilityIssue(
                            "blocker",
                            "DANGLING_SLOT_BINDING",
                            f"Binding {role!r} aponta para node inexistente.",
                            page.id,
                            slot_id,
                        )
                    )
            if slot.product_id:
                bound_slots += 1
                page_bound_slots += 1

        raw_blocks = page.metadata.get("semantic_blocks")
        if isinstance(raw_blocks, dict):
            page_card_count = 0
            for block_id, block in raw_blocks.items():
                if not isinstance(block, dict):
                    continue
                kind = str(block.get("kind") or "")
                if kind == "product_card":
                    product_cards += 1
                    page_card_count += 1
                elif kind == "price_block":
                    price_blocks += 1

                for member_id in block.get("members") or []:
                    if str(member_id) not in page.nodes:
                        issues.append(
                            UsabilityIssue(
                                "blocker",
                                "DANGLING_SEMANTIC_MEMBER",
                                "Bloco semântico aponta para node inexistente.",
                                page.id,
                                str(block_id),
                            )
                        )
            if page_card_count >= 2:
                multiproduct_found = True

        if len(page.slots) >= 2 or page_bound_slots >= 2:
            multiproduct_found = True

    if page_count and populated_pages == 0:
        issues.append(UsabilityIssue("blocker", "EMPTY_PROJECT", "Nenhuma página contém conteúdo visível."))

    if visible_nodes and editable_text_nodes == 0:
        issues.append(
            UsabilityIssue(
                "warning",
                "NO_EDITABLE_TEXT",
                "Não há texto visível desbloqueado para edição no projeto.",
            )
        )

    if visible_nodes and image_nodes == 0:
        issues.append(
            UsabilityIssue(
                "warning",
                "NO_IMAGES",
                "O projeto não possui imagens visíveis; confirme se o encarte importou os assets.",
            )
        )

    if smart_slots and bound_slots == 0:
        issues.append(
            UsabilityIssue(
                "info",
                "UNBOUND_SMART_SLOTS",
                "Há Smart Slots disponíveis, mas nenhum produto está aplicado.",
            )
        )

    if require_multi_product_page and not multiproduct_found:
        issues.append(
            UsabilityIssue(
                "blocker",
                "NO_MULTI_PRODUCT_PAGE",
                "Nenhuma página demonstra dois ou mais cards/slots de produto.",
            )
        )

    professional_usable = not any(issue.severity == "blocker" for issue in issues)
    return G2UsabilityReport(
        professional_usable=professional_usable,
        page_count=page_count,
        populated_pages=populated_pages,
        node_count=node_count,
        visible_nodes=visible_nodes,
        editable_text_nodes=editable_text_nodes,
        image_nodes=image_nodes,
        smart_slots=smart_slots,
        bound_slots=bound_slots,
        product_cards=product_cards,
        price_blocks=price_blocks,
        issues=issues,
    )
