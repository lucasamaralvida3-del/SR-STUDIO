from __future__ import annotations

"""SR Graphics Engine 2.0 — novo núcleo gráfico independente da UI."""

from .fidelity import (
    FidelityCase,
    FidelityMetrics,
    FidelityPolicy,
    FidelityResult,
    FidelitySuiteResult,
    compare_images,
    run_suite,
)
from .import_audit import ImportAuditIssue, ImportAuditReport, audit_import
from .model import (
    AssetRef,
    BindingRole,
    CoordinateUnit,
    FitMode,
    GraphicsDocument,
    GraphicsNode,
    GraphicsPage,
    NodeKind,
    Rect,
    SmartSlot,
    Transform,
)
from .operations import GraphicsSession
from .pptx_fidelity import EmbeddedPptxFont, PptxFidelityReport, enhance_pptx_document
from .preflight import PreflightIssue, run_preflight
from .qt_renderer import RenderReport, render_pdf, render_png

ENGINE_NAME = "SR Graphics Engine"
ENGINE_VERSION = "2.0.0-alpha.4"
SCHEMA_VERSION = "srscene/2.0"

__all__ = [
    "AssetRef",
    "BindingRole",
    "CoordinateUnit",
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "EmbeddedPptxFont",
    "FidelityCase",
    "FidelityMetrics",
    "FidelityPolicy",
    "FidelityResult",
    "FidelitySuiteResult",
    "FitMode",
    "GraphicsDocument",
    "GraphicsNode",
    "GraphicsPage",
    "GraphicsSession",
    "ImportAuditIssue",
    "ImportAuditReport",
    "NodeKind",
    "PptxFidelityReport",
    "PreflightIssue",
    "Rect",
    "RenderReport",
    "SCHEMA_VERSION",
    "SmartSlot",
    "Transform",
    "audit_import",
    "compare_images",
    "enhance_pptx_document",
    "render_pdf",
    "render_png",
    "run_preflight",
    "run_suite",
]