from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .model import GraphicsDocument, GraphicsNode, NodeKind


@dataclass(slots=True, frozen=True)
class PreflightIssue:
    severity: str
    code: str
    message: str
    page_id: str = ""
    node_id: str = ""


def run_preflight(document: GraphicsDocument, *, available_fonts: Iterable[str] | None = None) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    fonts = {str(name).strip().casefold() for name in available_fonts or []}
    if not document.pages:
        return [PreflightIssue("error", "NO_PAGES", "O projeto não possui páginas.")]
    for page in document.pages:
        if page.width <= 0 or page.height <= 0:
            issues.append(PreflightIssue("error", "INVALID_PAGE_SIZE", "Dimensão de página inválida.", page.id))
        roots_seen: set[str] = set()
        for root_id in page.roots:
            if root_id in roots_seen:
                issues.append(PreflightIssue("error", "DUPLICATE_ROOT", "Raiz duplicada.", page.id, root_id))
            roots_seen.add(root_id)
            if root_id not in page.nodes:
                issues.append(PreflightIssue("error", "MISSING_ROOT", "Raiz aponta para elemento ausente.", page.id, root_id))
        for node in page.nodes.values():
            issues.extend(_node_issues(document, page.id, page.width, page.height, node, page.nodes, fonts))
        for slot in page.slots.values():
            for role, node_id in slot.node_by_role.items():
                if node_id not in page.nodes:
                    issues.append(PreflightIssue("error", "SLOT_NODE_MISSING", f"Smart Slot '{slot.name}' aponta para elemento ausente em {role}.", page.id, node_id))
        issues.extend(_cycle_issues(page.id, page.nodes))
    return issues


def assert_document_integrity(document: GraphicsDocument) -> None:
    fatal = [issue for issue in run_preflight(document) if issue.severity == "error"]
    if fatal:
        first = fatal[0]
        raise ValueError(f"{first.code}: {first.message}")


def _node_issues(document: GraphicsDocument, page_id: str, page_width: float, page_height: float, node: GraphicsNode, nodes: dict[str, GraphicsNode], fonts: set[str]) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    t = node.transform
    if t.width < 0 or t.height < 0:
        issues.append(PreflightIssue("error", "NEGATIVE_SIZE", "Elemento possui dimensão negativa.", page_id, node.id))
    if node.opacity < 0 or node.opacity > 1:
        issues.append(PreflightIssue("error", "INVALID_OPACITY", "Opacidade fora de 0–1.", page_id, node.id))
    if node.parent_id and node.parent_id not in nodes:
        issues.append(PreflightIssue("error", "MISSING_PARENT", "Elemento aponta para grupo pai ausente.", page_id, node.id))
    for child_id in node.children:
        child = nodes.get(child_id)
        if child is None:
            issues.append(PreflightIssue("error", "MISSING_CHILD", "Grupo aponta para filho ausente.", page_id, node.id))
        elif child.parent_id != node.id:
            issues.append(PreflightIssue("error", "PARENT_CHILD_MISMATCH", "Relação pai/filho inconsistente.", page_id, child.id))
    if node.kind is NodeKind.IMAGE and node.asset_id and node.asset_id not in document.assets:
        issues.append(PreflightIssue("warning", "MISSING_ASSET", "Imagem referencia um asset não registrado.", page_id, node.id))
    if node.kind is NodeKind.TEXT:
        family = str(node.style.get("font_family") or "").strip()
        if fonts and family and family.casefold() not in fonts:
            issues.append(PreflightIssue("warning", "FONT_MISSING", f"Fonte não instalada: {family}", page_id, node.id))
        if not node.text and node.binding_role is None:
            issues.append(PreflightIssue("info", "EMPTY_TEXT", "Caixa de texto vazia.", page_id, node.id))
    margin = max(page_width, page_height) * 0.05
    if t.x + t.width < -margin or t.y + t.height < -margin or t.x > page_width + margin or t.y > page_height + margin:
        issues.append(PreflightIssue("warning", "OFF_PAGE", "Elemento está completamente fora da página.", page_id, node.id))
    return issues


def _cycle_issues(page_id: str, nodes: dict[str, GraphicsNode]) -> list[PreflightIssue]:
    issues: list[PreflightIssue] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    def walk(node_id: str) -> None:
        if node_id in visiting:
            issues.append(PreflightIssue("error", "GROUP_CYCLE", "Ciclo detectado na árvore de grupos.", page_id, node_id))
            return
        if node_id in visited or node_id not in nodes:
            return
        visiting.add(node_id)
        for child_id in nodes[node_id].children:
            walk(child_id)
        visiting.remove(node_id)
        visited.add(node_id)
    for node_id in nodes:
        walk(node_id)
    return issues
