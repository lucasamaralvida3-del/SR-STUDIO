from __future__ import annotations

"""Immutable export contract for the G2 flyer editor.

Exports must observe a stable snapshot of the SR Scene. A renderer is allowed to
cache/annotate its snapshot, but it must never mutate the live document being
edited. This module provides that boundary independently from Qt so it can be
validated with lightweight tests and reused by PNG/PDF/background jobs.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from .model import GraphicsDocument
from .scene_fingerprint import SceneFingerprint, fingerprint_document

T = TypeVar("T")


@dataclass(slots=True, frozen=True)
class ExportContractReport(Generic[T]):
    output: Path
    original_before: str
    original_after: str
    snapshot_before: str
    snapshot_after: str
    original_unchanged: bool
    snapshot_changed_by_exporter: bool
    result: T

    @property
    def safe(self) -> bool:
        return self.original_unchanged

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        value = result.get("result")
        if hasattr(self.result, "to_dict"):
            result["result"] = self.result.to_dict()
        elif isinstance(value, Path):
            result["result"] = str(value)
        result["output"] = str(self.output)
        result["safe"] = self.safe
        return result


def snapshot_document(document: GraphicsDocument) -> GraphicsDocument:
    """Deep-copy through the canonical schema rather than sharing runtime nodes."""
    return GraphicsDocument.from_dict(document.to_dict())


def run_snapshot_export(
    document: GraphicsDocument,
    output: str | Path,
    exporter: Callable[[GraphicsDocument, Path], T],
) -> ExportContractReport[T]:
    """Run an exporter against an isolated scene and prove live-scene immutability.

    The exporter may alter the snapshot, for example by attaching temporary
    diagnostics. That is reported but does not fail the contract. Any mutation
    of the live document raises immediately because it risks user data loss and
    preview/export drift.
    """

    target = Path(output)
    original_before = fingerprint_document(document).sha256
    snapshot = snapshot_document(document)
    snapshot_before = fingerprint_document(snapshot).sha256

    result = exporter(snapshot, target)

    snapshot_after = fingerprint_document(snapshot).sha256
    original_after = fingerprint_document(document).sha256
    original_unchanged = original_before == original_after
    report = ExportContractReport(
        output=target,
        original_before=original_before,
        original_after=original_after,
        snapshot_before=snapshot_before,
        snapshot_after=snapshot_after,
        original_unchanged=original_unchanged,
        snapshot_changed_by_exporter=snapshot_before != snapshot_after,
        result=result,
    )
    if not report.safe:
        raise RuntimeError("EXPORT_MUTATED_LIVE_SCENE: o exportador alterou o projeto aberto.")
    return report


def fingerprints_match_visual_structure(
    before: SceneFingerprint,
    after: SceneFingerprint,
) -> bool:
    """Explicit helper for pre/post export assertions and diagnostics."""
    return before.sha256 == after.sha256
