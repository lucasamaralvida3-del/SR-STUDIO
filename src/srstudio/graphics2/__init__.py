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
from .preflight import PreflightIssue, run_preflight
from .qt_renderer import RenderReport, render_pdf, render_png

ENGINE_NAME = "SR Graphics Engine"
ENGINE_VERSION = "2.0.0-alpha.2"
SCHEMA_VERSION = "srscene/2.0"

__all__ = [
    "AssetRef",
    "BindingRole",
    "CoordinateUnit",
    "ENGINE_NAME",
    "ENGINE_VERSION",
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
    "NodeKind",
    "PreflightIssue",
    "Rect",
    "RenderReport",
    "SCHEMA_VERSION",
    "SmartSlot",
    "Transform",
    "compare_images",
    "render_pdf",
    "render_png",
    "run_preflight",
    "run_suite",
]