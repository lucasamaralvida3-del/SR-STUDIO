from __future__ import annotations

"""Auditoria de risco para importações Canva/PPTX convertidas em SR Scene 2.0."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from .model import BindingRole, GraphicsDocument, GraphicsNode, NodeKind

Severity = Literal["error", "warning", "info"]


@dataclass(slots=True)
class ImportAuditIssue:
    severity: Severity
    code: str
    message: str
    page_id: str = ""
    node_id: str = ""


@dataclass(slots=True)
class ImportAuditReport:
    pages: int = 0
    nodes: int = 0
    slots: int = 0
    images: int = 0
    texts: int = 0
    issues: list[ImportAuditIssue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(issue.severity == "error" for issue in self.issues)

    @property
    def warnings(self) -> int:
        return sum(issue.severity == "warning" for issue in self.issues)

    @property
    def infos(self) -> int:
        return sum(issue.severity == "info" for issue in self.issues)

    @property
    def ready(self) -> bool:
        return self.errors == 0

    @property
    def confidence(self) -> float:
        # Erro representa risco estrutural; warning indica possível diferença
        # visual; info não reduz significativamente a confiança.
        denominator = max(1, self.nodes + self.slots * 2 + self.pages * 3)
        penalty = self.errors * 6.0 + self.warnings * 1.5 + self.infos * 0.1
        return max(0.0, min(1.0, 1.0 - penalty / denominator))

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "confidence": self.confidence,
            "pages": self.pages,
            "nodes": self.nodes,
            "slots": self.slots,
            "images": self.images,
            "texts": self.texts,
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": self.infos,
            "issues": [asdict(issue) for issue in self.issues],
        }


def audit_import(document: GraphicsDocument, *, check_local_assets: bool = True) -> ImportAuditReport:
    report = ImportAuditReport(pages=len(document.pages))
    if not document.pages:
        report.issues.append(ImportAuditIssue("error", "NO_PAGES", "Documento importado sem páginas."))
        return report

    for page in document.pages:
        if page.width <= 0 or page.height <= 0:
            report.issues.append(
                ImportAuditIssue(
                    "error",
                    "INVALID_PAGE_SIZE",
                    f"Página com dimensão inválida: {page.width}x{page.height}.",
                    page_id=page.id,
                )
            )
        report.nodes += len(page.nodes)
        report.slots += len(page.slots)

        for node in page.nodes.values():
            _audit_node(document, page, node, report, check_local_assets=check_local_assets)
        for slot in page.slots.values():
            _audit_slot(page, slot, report)

    document.metadata["graphics2_import_audit"] = report.to_dict()
    return report


def _audit_node(document, page, node: GraphicsNode, report: ImportAuditReport, *, check_local_assets: bool) -> None:
    if node.kind is NodeKind.TEXT:
        report.texts += 1
    elif node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
        report.images += 1

    t = node.transform
    if t.width < 0 or t.height < 0:
        report.issues.append(
            ImportAuditIssue(
                "error",
                "NEGATIVE_GEOMETRY",
                "Elemento possui largura/altura negativa.",
                page.id,
                node.id,
            )
        )
    if node.visible and (t.width <= 0 or t.height <= 0) and node.kind not in {NodeKind.LINE, NodeKind.GROUP}:
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "ZERO_GEOMETRY",
                "Elemento visível possui dimensão zero.",
                page.id,
                node.id,
            )
        )

    if node.visible and _outside_page(node, page.width, page.height):
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "OUTSIDE_PAGE",
                "Elemento importado está totalmente fora dos limites da página.",
                page.id,
                node.id,
            )
        )

    if node.kind is NodeKind.TEXT:
        family = str(node.style.get("font_family") or "").strip()
        if not family:
            report.issues.append(
                ImportAuditIssue("warning", "FONT_UNSPECIFIED", "Texto sem família tipográfica definida.", page.id, node.id)
            )
        source_family = str(node.style.get("source_font_family") or node.metadata.get("source_font_name") or "").strip()
        if source_family and family and source_family.casefold() != family.casefold():
            report.issues.append(
                ImportAuditIssue(
                    "info",
                    "FONT_SUBSTITUTION",
                    f"Fonte de origem '{source_family}' está sendo exibida como '{family}'.",
                    page.id,
                    node.id,
                )
            )

    if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
        source = str(node.metadata.get("bound_image_source") or "").strip()
        asset = document.assets.get(node.asset_id) if node.asset_id else None
        if not source and asset is not None:
            source = str(asset.source or "").strip()
        if not source:
            report.issues.append(
                ImportAuditIssue("warning", "IMAGE_SOURCE_MISSING", "Imagem sem origem resolvida.", page.id, node.id)
            )
        elif check_local_assets and not _is_nonlocal(source) and not Path(source).is_file():
            report.issues.append(
                ImportAuditIssue(
                    "warning",
                    "IMAGE_FILE_MISSING",
                    f"Arquivo de imagem não encontrado: {source}",
                    page.id,
                    node.id,
                )
            )

    if node.kind is NodeKind.PATH and not node.style.get("path") and not node.metadata.get("shape_geometry"):
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "PATH_GEOMETRY_MISSING",
                "Path importado sem geometria vetorial explícita.",
                page.id,
                node.id,
            )
        )


def _audit_slot(page, slot, report: ImportAuditReport) -> None:
    bindings = slot.node_by_role
    required_groups = (
        (BindingRole.NAME.value,),
        (BindingRole.IMAGE.value,),
        (BindingRole.PRICE_REAIS.value, BindingRole.RETAIL_PRICE.value),
    )
    for alternatives in required_groups:
        if not any(role in bindings for role in alternatives):
            report.issues.append(
                ImportAuditIssue(
                    "warning",
                    "SLOT_BINDING_MISSING",
                    f"Smart Slot '{slot.name or slot.id}' sem binding obrigatório: {'/'.join(alternatives)}.",
                    page.id,
                )
            )
    for role, node_id in bindings.items():
        if node_id not in page.nodes:
            report.issues.append(
                ImportAuditIssue(
                    "error",
                    "SLOT_NODE_MISSING",
                    f"Smart Slot referencia node inexistente em '{role}': {node_id}.",
                    page.id,
                    node_id,
                )
            )


def _outside_page(node: GraphicsNode, page_width: float, page_height: float) -> bool:
    rect = node.transform.rect.normalized()
    return rect.right <= 0 or rect.bottom <= 0 or rect.x >= page_width or rect.y >= page_height


def _is_nonlocal(source: str) -> bool:
    lowered = source.lower()
    return lowered.startswith(("http://", "https://", "data:", "qrc:/", "file://"))
