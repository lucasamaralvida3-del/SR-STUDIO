from __future__ import annotations

from dataclasses import dataclass
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


def inspect_quality(document: GraphicsDocument, *, available_fonts=None) -> QualityReport:
    issues = tuple(run_preflight(document, available_fonts=available_fonts)); errors = sum(issue.severity == "error" for issue in issues); warnings = sum(issue.severity == "warning" for issue in issues); infos = sum(issue.severity == "info" for issue in issues)
    score = max(0, min(100, 100 - errors * 25 - warnings * 6 - infos))
    return QualityReport(score=score, issues=issues, errors=errors, warnings=warnings, infos=infos)
