from __future__ import annotations

"""SR Graphics Engine 2.0 — novo núcleo gráfico independente da UI."""

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

ENGINE_NAME = "SR Graphics Engine"
ENGINE_VERSION = "2.0.0-alpha.1"
SCHEMA_VERSION = "srscene/2.0"

__all__ = [
    "AssetRef", "BindingRole", "CoordinateUnit", "ENGINE_NAME", "ENGINE_VERSION",
    "FitMode", "GraphicsDocument", "GraphicsNode", "GraphicsPage", "GraphicsSession",
    "NodeKind", "PreflightIssue", "Rect", "SCHEMA_VERSION", "SmartSlot", "Transform",
    "run_preflight",
]
