from __future__ import annotations

"""SR Graphics Engine 2.0 — novo núcleo gráfico independente da UI."""

from .drop_target import DropTarget, find_drop_target, smart_slot_bounds
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
from .pdf_baseline import PdfBaselinePage, render_pdf_baselines
from .pptx_fidelity import EmbeddedPptxFont, PptxFidelityReport, enhance_pptx_document
from .pptx_groups import PptxGroupReport, rebuild_pptx_groups
from .pptx_structure import PptxMappingAudit, PptxSlideStructure, PptxStructureReport, inspect_pptx_structure
from .preflight import PreflightIssue, run_preflight
from .quality import ProductionGateIssue, ProductionGateReport, inspect_production_gate, store_visual_fidelity
from .qt_renderer import RenderReport, render_pdf, render_png
from .scene_fingerprint import PageFingerprint, SceneFingerprint, fingerprint_document, store_scene_fingerprint
from .semantic_blocks import (
    SemanticBlock,
    SemanticBlockReport,
    build_semantic_blocks,
    semantic_block,
    semantic_member_ids,
    semantic_owner,
)
from .semantic_placeholders import PlaceholderRecoveryReport, recover_canva_image_placeholders
from .semantic_recovery import recover_canva_semantic_cards

ENGINE_NAME = "SR Graphics Engine"
ENGINE_VERSION = "2.0.0-alpha.18"
SCHEMA_VERSION = "srscene/2.0"

__all__ = [
    "AssetRef",
    "BindingRole",
    "CoordinateUnit",
    "DropTarget",
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
    "PageFingerprint",
    "PdfBaselinePage",
    "PlaceholderRecoveryReport",
    "PptxFidelityReport",
    "PptxGroupReport",
    "PptxMappingAudit",
    "PptxSlideStructure",
    "PptxStructureReport",
    "PreflightIssue",
    "ProductionGateIssue",
    "ProductionGateReport",
    "Rect",
    "RenderReport",
    "SCHEMA_VERSION",
    "SceneFingerprint",
    "SemanticBlock",
    "SemanticBlockReport",
    "SmartSlot",
    "Transform",
    "audit_import",
    "build_semantic_blocks",
    "compare_images",
    "enhance_pptx_document",
    "find_drop_target",
    "fingerprint_document",
    "inspect_pptx_structure",
    "inspect_production_gate",
    "rebuild_pptx_groups",
    "recover_canva_image_placeholders",
    "recover_canva_semantic_cards",
    "render_pdf",
    "render_pdf_baselines",
    "render_png",
    "run_preflight",
    "run_suite",
    "semantic_block",
    "semantic_member_ids",
    "semantic_owner",
    "smart_slot_bounds",
    "store_scene_fingerprint",
    "store_visual_fidelity",
]
