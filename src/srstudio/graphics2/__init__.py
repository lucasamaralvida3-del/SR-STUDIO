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
from .fidelity_attribution import (
    FidelityAttributionReport,
    FidelityNodeSuspect,
    FidelityRegionAttribution,
    attribute_fidelity_regions,
)
from .fidelity_diagnostics import TRIAGE_METADATA_KEY, compact_fidelity_triage, store_fidelity_triage
from .fidelity_triage import (
    FidelityRegion,
    FidelityTriageReport,
    analyze_fidelity_regions,
    write_triage_report,
)
from .image_crop import CropInsets, crop_pixel_box, normalize_crop, update_crop
from .image_fill import FillDestination, drawingml_fill_destination, has_drawingml_fill_rect, normalize_fill_rect
from .import_audit import ImportAuditIssue, ImportAuditReport, audit_import
from .legacy_merge import (
    LEGACY_SOURCE_SNAPSHOT_KEY,
    LegacyMergeConflict,
    LegacyMergeReport,
    analyze_legacy_merge,
    merge_graphics_to_studio_non_conflicting,
    resolve_legacy_merge_conflicts,
)
from .legacy_sync import (
    LegacySyncReport,
    fingerprint_studio_project,
    sync_graphics_to_studio,
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
from .pdf_baseline import PdfBaselinePage, render_pdf_baselines
from .pptx_effect_mapping import (
    PptxEffectMappingIssue,
    PptxEffectMappingReport,
    PptxEffectNodeMapping,
    map_pptx_effects_to_document,
)
from .pptx_effects import PptxEffectAudit, ShapeEffectStats, SlideEffectStats, audit_pptx_effects
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
from .studio_bridge import (
    StudioBridgeLaunchResult,
    StudioBridgePreparation,
    StudioBridgeSyncResult,
    bridge_flags,
    launch_studio_project_if_enabled,
    prepare_studio_project,
    sync_saved_session_to_project,
)
from .saved_merge import analyze_saved_session_merge, resolve_saved_session_merge

ENGINE_NAME = "SR Graphics Engine"
ENGINE_VERSION = "2.0.0-alpha.37"
SCHEMA_VERSION = "srscene/2.0"

__all__ = [
    "AssetRef",
    "BindingRole",
    "CoordinateUnit",
    "CropInsets",
    "DropTarget",
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "EmbeddedPptxFont",
    "FidelityAttributionReport",
    "FidelityCase",
    "FidelityMetrics",
    "FidelityNodeSuspect",
    "FidelityPolicy",
    "FidelityRegion",
    "FidelityRegionAttribution",
    "FidelityResult",
    "FidelitySuiteResult",
    "FidelityTriageReport",
    "FillDestination",
    "FitMode",
    "GraphicsDocument",
    "GraphicsNode",
    "GraphicsPage",
    "GraphicsSession",
    "ImportAuditIssue",
    "ImportAuditReport",
    "LEGACY_SOURCE_SNAPSHOT_KEY",
    "LegacyMergeConflict",
    "LegacyMergeReport",
    "LegacySyncReport",
    "NodeKind",
    "PageFingerprint",
    "PdfBaselinePage",
    "PlaceholderRecoveryReport",
    "PptxEffectAudit",
    "PptxEffectMappingIssue",
    "PptxEffectMappingReport",
    "PptxEffectNodeMapping",
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
    "ShapeEffectStats",
    "SlideEffectStats",
    "SmartSlot",
    "StudioBridgeLaunchResult",
    "StudioBridgePreparation",
    "StudioBridgeSyncResult",
    "TRIAGE_METADATA_KEY",
    "Transform",
    "analyze_fidelity_regions",
    "analyze_legacy_merge",
    "analyze_saved_session_merge",
    "attribute_fidelity_regions",
    "audit_import",
    "audit_pptx_effects",
    "bridge_flags",
    "build_semantic_blocks",
    "compact_fidelity_triage",
    "compare_images",
    "crop_pixel_box",
    "drawingml_fill_destination",
    "enhance_pptx_document",
    "find_drop_target",
    "fingerprint_document",
    "fingerprint_studio_project",
    "has_drawingml_fill_rect",
    "inspect_pptx_structure",
    "inspect_production_gate",
    "launch_studio_project_if_enabled",
    "map_pptx_effects_to_document",
    "merge_graphics_to_studio_non_conflicting",
    "normalize_crop",
    "normalize_fill_rect",
    "prepare_studio_project",
    "rebuild_pptx_groups",
    "recover_canva_image_placeholders",
    "recover_canva_semantic_cards",
    "render_pdf",
    "render_pdf_baselines",
    "render_png",
    "resolve_legacy_merge_conflicts",
    "resolve_saved_session_merge",
    "run_preflight",
    "run_suite",
    "semantic_block",
    "semantic_member_ids",
    "semantic_owner",
    "smart_slot_bounds",
    "store_fidelity_triage",
    "store_scene_fingerprint",
    "store_visual_fidelity",
    "sync_graphics_to_studio",
    "sync_saved_session_to_project",
    "update_crop",
    "write_triage_report",
]
