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
    """Combina preflight, import audit, fidelidade OOXML e Golden Master.

    O gate pode ser usado em duas fases:
    - durante o desenvolvimento, ``require_visual_fidelity=False`` permite editar
      documentos ainda sem um Golden Master;
    - para ativação/release, ``require_visual_fidelity=True`` exige que a última
      comparação visual tenha passado antes do Engine 2 ser considerado pronto.
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
