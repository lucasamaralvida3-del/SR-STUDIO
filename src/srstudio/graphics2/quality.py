from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .model import GraphicsDocument
from .preflight import PreflightIssue, run_preflight


@dataclass(slots=True, frozen=True)
class QualityReport:
    score: int
    issues: tuple[PreflightIssue, ...]
    errors: int
    warnings: int
    infos: int

    @property
    def production_ready(self) -> bool:
        return self.errors == 0 and self.score >= 90


@dataclass(slots=True, frozen=True)
class ProductionGateIssue:
    severity: Literal["blocker", "warning", "info"]
    code: str
    message: str


@dataclass(slots=True)
class ProductionGateReport:
    ready: bool
    score: int
    structural_score: int
    import_confidence: float
    visual_score: float | None
    visual_passed: bool | None
    visual_required: bool
    embedded_fonts_declared: int
    embedded_fonts_extracted: int
    mapping_page_count_match: bool = True
    mapping_text_coverage: float = 1.0
    mapping_autofit_coverage: float = 1.0
    mapping_image_coverage: float = 1.0
    mapping_group_coverage: float = 1.0
    mapping_fill_rect_coverage: float = 1.0
    mapping_fill_outset_coverage: float = 1.0
    mapping_image_clip_coverage: float = 1.0
    issues: list[ProductionGateIssue] = field(default_factory=list)

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


def inspect_quality(document: GraphicsDocument, *, available_fonts=None) -> QualityReport:
    issues = tuple(run_preflight(document, available_fonts=available_fonts))
    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)
    infos = sum(issue.severity == "info" for issue in issues)
    score = max(0, min(100, 100 - errors * 25 - warnings * 6 - infos))
    return QualityReport(score=score, issues=issues, errors=errors, warnings=warnings, infos=infos)


def inspect_production_gate(
    document: GraphicsDocument,
    *,
    available_fonts=None,
    require_visual_fidelity: bool = False,
    minimum_score: int = 90,
) -> ProductionGateReport:
    """Combina preflight, import audit, mapeamento OOXML e Golden Master.

    O gate pode ser usado em duas fases:
    - durante o desenvolvimento, ``require_visual_fidelity=False`` permite editar
      documentos ainda sem um Golden Master;
    - para ativação/release, ``require_visual_fidelity=True`` exige que a última
      comparação visual tenha passado antes do Engine 2 ser considerado pronto.

    Para PPTX, cobertura de páginas/textos/imagens, contratos de auto-fit e
    enquadramento DrawingML é parte do score. Isso evita aprovar uma cena
    internamente válida quando o conversor perdeu conteúdo, tipografia semântica,
    fillRect ou máscara existentes na fonte.
    """

    structural = inspect_quality(document, available_fonts=available_fonts)
    issues: list[ProductionGateIssue] = []
    if structural.errors:
        issues.append(
            ProductionGateIssue(
                "blocker",
                "PREFLIGHT_ERRORS",
                f"Preflight possui {structural.errors} erro(s) estrutural(is).",
            )
        )
    elif structural.warnings:
        issues.append(
            ProductionGateIssue(
                "warning",
                "PREFLIGHT_WARNINGS",
                f"Preflight possui {structural.warnings} aviso(s).",
            )
        )

    metadata = dict(document.metadata or {})
    audit = dict(metadata.get("graphics2_import_audit") or {})
    import_confidence = _clamp01(audit.get("confidence", 1.0))
    audit_errors = _as_int(audit.get("errors", 0))
    audit_warnings = _as_int(audit.get("warnings", 0))
    if audit_errors:
        issues.append(
            ProductionGateIssue(
                "blocker",
                "IMPORT_AUDIT_FAILED",
                f"Auditoria de importação possui {audit_errors} erro(s).",
            )
        )
    elif audit_warnings:
        issues.append(
            ProductionGateIssue(
                "warning",
                "IMPORT_AUDIT_WARNINGS",
                f"Auditoria de importação possui {audit_warnings} aviso(s).",
            )
        )

    mapping = dict(metadata.get("pptx_mapping_audit") or {})
    mapping_page_match = bool(mapping.get("page_count_match", True))
    mapping_text = _clamp01(mapping.get("text_coverage", 1.0))
    mapping_autofit = _clamp01(mapping.get("autofit_coverage", 1.0))
    mapping_image = _clamp01(mapping.get("image_coverage", 1.0))
    mapping_group = _clamp01(mapping.get("group_coverage", 1.0))
    mapping_fill_rect = _clamp01(mapping.get("fill_rect_coverage", 1.0))
    mapping_fill_outset = _clamp01(mapping.get("fill_outset_coverage", 1.0))
    mapping_image_clip = _clamp01(mapping.get("image_clip_coverage", 1.0))
    source_text = _as_int(mapping.get("source_text_shapes", 0))
    source_autofit = _as_int(mapping.get("source_autofit_contracts", 0))
    source_images = _as_int(mapping.get("source_image_shapes", 0))
    source_groups = _as_int(mapping.get("source_groups", 0))
    source_fill_rects = _as_int(mapping.get("source_fill_rects", 0))
    source_fill_outsets = _as_int(mapping.get("source_fill_outsets", 0))
    source_image_clips = _as_int(mapping.get("source_image_custom_geometry", 0))
    if mapping:
        if not mapping_page_match:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "PPTX_PAGE_COVERAGE_FAILED",
                    "Quantidade de páginas importadas diverge do PPTX fonte.",
                )
            )
        if source_text >= 4 and mapping_text < 0.70:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "PPTX_TEXT_COVERAGE_FAILED",
                    f"Cobertura de textos OOXML crítica: {mapping_text * 100:.2f}%.",
                )
            )
        elif source_text >= 4 and mapping_text < 0.90:
            issues.append(
                ProductionGateIssue(
                    "warning",
                    "PPTX_TEXT_COVERAGE_LOW",
                    f"Cobertura de textos OOXML abaixo do alvo: {mapping_text * 100:.2f}%.",
                )
            )
        if source_autofit >= 4 and mapping_autofit < 0.80:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "PPTX_AUTOFIT_COVERAGE_FAILED",
                    f"Cobertura semântica de auto-fit OOXML crítica: {mapping_autofit * 100:.2f}%.",
                )
            )
        elif source_autofit >= 4 and mapping_autofit < 0.95:
            issues.append(
                ProductionGateIssue(
                    "warning",
                    "PPTX_AUTOFIT_COVERAGE_LOW",
                    f"Cobertura semântica de auto-fit OOXML abaixo do alvo: {mapping_autofit * 100:.2f}%.",
                )
            )
        if source_images >= 2 and mapping_image < 0.60:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "PPTX_IMAGE_COVERAGE_FAILED",
                    f"Cobertura de imagens OOXML crítica: {mapping_image * 100:.2f}%.",
                )
            )
        elif source_images >= 2 and mapping_image < 0.85:
            issues.append(
                ProductionGateIssue(
                    "warning",
                    "PPTX_IMAGE_COVERAGE_LOW",
                    f"Cobertura de imagens OOXML abaixo do alvo: {mapping_image * 100:.2f}%.",
                )
            )
        if source_groups >= 2 and mapping_group < 0.50:
            issues.append(
                ProductionGateIssue(
                    "warning",
                    "PPTX_GROUP_COVERAGE_LOW",
                    f"Cobertura de grupos DrawingML baixa: {mapping_group * 100:.2f}%.",
                )
            )
        if source_fill_rects and mapping_fill_rect < 0.80:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "PPTX_FILL_RECT_COVERAGE_FAILED",
                    f"Cobertura de stretch/fillRect DrawingML crítica: {mapping_fill_rect * 100:.2f}%.",
                )
            )
        elif source_fill_rects and mapping_fill_rect < 0.95:
            issues.append(
                ProductionGateIssue(
                    "warning",
                    "PPTX_FILL_RECT_COVERAGE_LOW",
                    f"Cobertura de stretch/fillRect DrawingML abaixo do alvo: {mapping_fill_rect * 100:.2f}%.",
                )
            )
        if source_fill_outsets and mapping_fill_outset < 0.80:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "PPTX_FILL_OUTSET_COVERAGE_FAILED",
                    f"Cobertura de fillRect com outset negativo crítica: {mapping_fill_outset * 100:.2f}%.",
                )
            )
        elif source_fill_outsets and mapping_fill_outset < 0.95:
            issues.append(
                ProductionGateIssue(
                    "warning",
                    "PPTX_FILL_OUTSET_COVERAGE_LOW",
                    f"Cobertura de fillRect com outset negativo abaixo do alvo: {mapping_fill_outset * 100:.2f}%.",
                )
            )
        if source_image_clips and mapping_image_clip < 0.80:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "PPTX_IMAGE_CLIP_COVERAGE_FAILED",
                    f"Cobertura de máscaras custGeom irregulares crítica: {mapping_image_clip * 100:.2f}%.",
                )
            )
        elif source_image_clips and mapping_image_clip < 0.95:
            issues.append(
                ProductionGateIssue(
                    "warning",
                    "PPTX_IMAGE_CLIP_COVERAGE_LOW",
                    f"Cobertura de máscaras custGeom irregulares abaixo do alvo: {mapping_image_clip * 100:.2f}%.",
                )
            )

    pptx = dict(metadata.get("pptx_fidelity") or {})
    fonts_declared = _as_int(pptx.get("fonts_declared", 0))
    fonts_extracted = _as_int(pptx.get("fonts_extracted", 0))
    if fonts_declared and fonts_extracted < fonts_declared:
        issues.append(
            ProductionGateIssue(
                "blocker",
                "EMBEDDED_FONTS_INCOMPLETE",
                f"PPTX declarou {fonts_declared} fonte(s) embutida(s), mas apenas {fonts_extracted} foram extraídas.",
            )
        )
    pptx_warnings = list(pptx.get("warnings") or [])
    if pptx_warnings:
        issues.append(
            ProductionGateIssue(
                "warning",
                "PPTX_FIDELITY_WARNINGS",
                f"Camada OOXML de fidelidade reportou {len(pptx_warnings)} aviso(s).",
            )
        )

    visual = dict(metadata.get("visual_fidelity_last") or {})
    visual_score: float | None = None
    visual_passed: bool | None = None
    if visual:
        visual_passed = bool(visual.get("passed", False))
        metrics = dict(visual.get("metrics") or {})
        visual_score = _clamp01(metrics.get("score", 0.0))
        if not visual_passed:
            issues.append(
                ProductionGateIssue(
                    "blocker",
                    "VISUAL_FIDELITY_FAILED",
                    f"Última comparação visual falhou com score {visual_score * 100:.4f}%.",
                )
            )
    elif require_visual_fidelity:
        issues.append(
            ProductionGateIssue(
                "blocker",
                "VISUAL_FIDELITY_MISSING",
                "Documento ainda não passou por comparação com Golden Master.",
            )
        )

    score_candidates = [float(structural.score), import_confidence * 100.0]
    if mapping:
        # Grupos são editabilidade/semântica e não entram no score visual puro;
        # páginas, texto, auto-fit, imagem, fillRect e máscaras são conteúdo perceptível.
        mapping_score = min(
            1.0 if mapping_page_match else 0.0,
            mapping_text if source_text else 1.0,
            mapping_autofit if source_autofit else 1.0,
            mapping_image if source_images else 1.0,
            mapping_fill_rect if source_fill_rects else 1.0,
            mapping_fill_outset if source_fill_outsets else 1.0,
            mapping_image_clip if source_image_clips else 1.0,
        )
        score_candidates.append(mapping_score * 100.0)
    if visual_score is not None:
        score_candidates.append(visual_score * 100.0)
    score = int(round(min(score_candidates))) if score_candidates else 0
    score = max(0, min(100, score - min(10, len(pptx_warnings) * 2)))
    blocker_count = sum(issue.severity == "blocker" for issue in issues)
    ready = blocker_count == 0 and score >= int(minimum_score)
    if blocker_count == 0 and score < int(minimum_score):
        issues.append(
            ProductionGateIssue(
                "blocker",
                "QUALITY_SCORE_BELOW_GATE",
                f"Score de produção {score} abaixo do mínimo {int(minimum_score)}.",
            )
        )
        ready = False

    return ProductionGateReport(
        ready=ready,
        score=score,
        structural_score=structural.score,
        import_confidence=import_confidence,
        visual_score=visual_score,
        visual_passed=visual_passed,
        visual_required=bool(require_visual_fidelity),
        embedded_fonts_declared=fonts_declared,
        embedded_fonts_extracted=fonts_extracted,
        mapping_page_count_match=mapping_page_match,
        mapping_text_coverage=mapping_text,
        mapping_autofit_coverage=mapping_autofit,
        mapping_image_coverage=mapping_image,
        mapping_group_coverage=mapping_group,
        mapping_fill_rect_coverage=mapping_fill_rect,
        mapping_fill_outset_coverage=mapping_fill_outset,
        mapping_image_clip_coverage=mapping_image_clip,
        issues=issues,
    )


def store_visual_fidelity(document: GraphicsDocument, result: Any) -> None:
    """Persiste somente o relatório serializável da última comparação visual."""

    if hasattr(result, "to_dict"):
        payload = result.to_dict()
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        raise TypeError("Resultado de fidelidade deve possuir to_dict() ou ser dict.")
    document.metadata["visual_fidelity_last"] = payload


def _clamp01(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0