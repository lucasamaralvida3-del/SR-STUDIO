from __future__ import annotations

"""Auditoria de risco para importações Canva/PPTX convertidas em SR Scene 2.0."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from .image_fill import has_drawingml_fill_rect, normalize_fill_rect
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
    image_clips: int = 0
    drawingml_fill_rects: int = 0
    drawingml_fill_outsets: int = 0
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
            "image_clips": self.image_clips,
            "drawingml_fill_rects": self.drawingml_fill_rects,
            "drawingml_fill_outsets": self.drawingml_fill_outsets,
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

    _audit_pptx_mapping(document, report)
    document.metadata["graphics2_import_audit"] = report.to_dict()
    return report


def _audit_pptx_mapping(document: GraphicsDocument, report: ImportAuditReport) -> None:
    """Transforma perda entre OOXML fonte e SR Scene em risco de importação.

    Esta camada é deliberadamente conservadora: diferenças moderadas viram
    warning; perda severa de páginas/imagens/fillRect/máscaras vira error e
    impede o Production Gate de aprovar silenciosamente um PPTX incompleto.
    """

    mapping = document.metadata.get("pptx_mapping_audit")
    if not isinstance(mapping, dict) or not mapping:
        return

    if not bool(mapping.get("page_count_match", True)):
        report.issues.append(
            ImportAuditIssue(
                "error",
                "PPTX_PAGE_MAPPING_LOSS",
                "Quantidade de páginas do SR Scene diverge da estrutura OOXML do PPTX.",
            )
        )

    text_coverage = _coverage_value(mapping.get("text_coverage", 1.0))
    image_coverage = _coverage_value(mapping.get("image_coverage", 1.0))
    group_coverage = _coverage_value(mapping.get("group_coverage", 1.0))
    fill_rect_coverage = _coverage_value(mapping.get("fill_rect_coverage", 1.0))
    fill_outset_coverage = _coverage_value(mapping.get("fill_outset_coverage", 1.0))
    image_clip_coverage = _coverage_value(mapping.get("image_clip_coverage", 1.0))
    source_text = _int(mapping.get("source_text_shapes", 0))
    source_images = _int(mapping.get("source_image_shapes", 0))
    source_groups = _int(mapping.get("source_groups", 0))
    source_fill_rects = _int(mapping.get("source_fill_rects", 0))
    source_fill_outsets = _int(mapping.get("source_fill_outsets", 0))
    source_image_clips = _int(mapping.get("source_image_custom_geometry", 0))

    if source_text >= 4 and text_coverage < 0.70:
        report.issues.append(
            ImportAuditIssue(
                "error",
                "PPTX_TEXT_MAPPING_LOSS",
                f"Apenas {text_coverage * 100:.2f}% dos textos OOXML chegaram ao SR Scene.",
            )
        )
    elif source_text >= 4 and text_coverage < 0.90:
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "PPTX_TEXT_MAPPING_RISK",
                f"Cobertura de textos OOXML abaixo do alvo: {text_coverage * 100:.2f}%.",
            )
        )

    if source_images >= 2 and image_coverage < 0.60:
        report.issues.append(
            ImportAuditIssue(
                "error",
                "PPTX_IMAGE_MAPPING_LOSS",
                f"Apenas {image_coverage * 100:.2f}% das imagens OOXML chegaram ao SR Scene. "
                "A importação pode ter ignorado formas Canva com a:blipFill.",
            )
        )
    elif source_images >= 2 and image_coverage < 0.85:
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "PPTX_IMAGE_MAPPING_RISK",
                f"Cobertura de imagens OOXML abaixo do alvo: {image_coverage * 100:.2f}%.",
            )
        )

    if source_groups >= 2 and group_coverage < 0.50:
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "PPTX_GROUP_MAPPING_RISK",
                f"Cobertura de grupos DrawingML baixa: {group_coverage * 100:.2f}%.",
            )
        )

    if source_fill_rects and fill_rect_coverage < 0.80:
        report.issues.append(
            ImportAuditIssue(
                "error",
                "PPTX_FILL_RECT_MAPPING_LOSS",
                f"Apenas {fill_rect_coverage * 100:.2f}% dos stretch/fillRect DrawingML foram preservados. "
                "Fotos do Canva podem usar enquadramento incorreto.",
            )
        )
    elif source_fill_rects and fill_rect_coverage < 0.95:
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "PPTX_FILL_RECT_MAPPING_RISK",
                f"Cobertura de stretch/fillRect DrawingML abaixo do alvo: {fill_rect_coverage * 100:.2f}%.",
            )
        )

    if source_fill_outsets and fill_outset_coverage < 0.80:
        report.issues.append(
            ImportAuditIssue(
                "error",
                "PPTX_FILL_OUTSET_MAPPING_LOSS",
                f"Apenas {fill_outset_coverage * 100:.2f}% dos fillRect com outset negativo foram preservados.",
            )
        )
    elif source_fill_outsets and fill_outset_coverage < 0.95:
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "PPTX_FILL_OUTSET_MAPPING_RISK",
                f"Cobertura de fillRect com outset negativo abaixo do alvo: {fill_outset_coverage * 100:.2f}%.",
            )
        )

    if source_image_clips and image_clip_coverage < 0.80:
        report.issues.append(
            ImportAuditIssue(
                "error",
                "PPTX_IMAGE_CLIP_MAPPING_LOSS",
                f"Apenas {image_clip_coverage * 100:.2f}% das máscaras custGeom irregulares de imagem foram preservadas.",
            )
        )
    elif source_image_clips and image_clip_coverage < 0.95:
        report.issues.append(
            ImportAuditIssue(
                "warning",
                "PPTX_IMAGE_CLIP_MAPPING_RISK",
                f"Cobertura de máscaras custGeom irregulares abaixo do alvo: {image_clip_coverage * 100:.2f}%.",
            )
        )


def _audit_node(document, page, node: GraphicsNode, report: ImportAuditReport, *, check_local_assets: bool) -> None:
    if node.kind is NodeKind.TEXT:
        report.texts += 1
    elif node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
        report.images += 1
        if isinstance(node.metadata.get("clip_path"), dict):
            report.image_clips += 1
        fill_rect = node.style.get("fill_rect")
        if has_drawingml_fill_rect(fill_rect):
            report.drawingml_fill_rects += 1
            normalized = normalize_fill_rect(fill_rect)
            if any(value < 0.0 for value in normalized.values()):
                report.drawingml_fill_outsets += 1

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


def _coverage_value(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
