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
from .page_duplicate import clone_page_with_fresh_ids, install_safe_page_duplication
from .pdf_baseline import PdfBaselinePage, render_pdf_baselines
from .pptx_artwork import PptxArtworkIssue, PptxArtworkRecoveryReport, recover_pptx_artwork
from .pptx_effect_mapping import (
    PptxEffectMappingIssue,
    PptxEffectMappingReport,
    PptxEffectNodeMapping,
    map_pptx_effects_to_document,
)
from .pptx_effects import PptxEffectAudit, ShapeEffectStats, SlideEffectStats, audit_pptx_effects
from .pptx_fidelity import EmbeddedPptxFont, PptxFidelityReport, enhance_pptx_document
from .pptx_fill_rect import (
    PptxFillRectContract,
    PptxFillRectIssue,
    PptxFillRectRecoveryReport,
    recover_pptx_fill_rects,
)
from .pptx_groups import PptxGroupReport, rebuild_pptx_groups
from .pptx_spacing import PptxSpacingIssue, PptxSpacingRecoveryReport, recover_pptx_spacing
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

# CHAT 4 was developed on top of these runtime guards. They are explicit here
# because the official integration base does not include the older 89c package
# bootstrap that used to install them implicitly.
from . import semantic_blocks as _semantic_blocks
from . import semantic_named_slot_runtime as _semantic_named_slots
from .product_semantic_compat import install_product_semantic_compat_guard
from .semantic_runtime import install_semantic_recovery_guard

install_semantic_recovery_guard(_semantic_blocks)
install_product_semantic_compat_guard(_semantic_blocks, _semantic_named_slots)
build_semantic_blocks = _semantic_blocks.build_semantic_blocks

from . import import_bridge as _import_bridge
from .binding_runtime import install_template_aware_binding_guard

install_template_aware_binding_guard(_import_bridge)

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

from . import command_router as _command_router
from .command_router import GraphicsCommandRouter
from .product_card_runtime import (
    ProductCardCreation,
    install_product_card_commands,
    install_product_card_runtime,
)
from .product_data_runtime import ProductUpdateResult, install_product_data_runtime

ENGINE_NAME = "SR Graphics Engine"
ENGINE_VERSION = "2.0.0-alpha.43"
SCHEMA_VERSION = "srscene/2.0"

# Safe duplication is a prerequisite for ProductCards/SmartSlots in multipage
# documents: every duplicated page must receive fresh internal identities.
install_safe_page_duplication(GraphicsSession)
install_product_card_runtime(GraphicsSession, _semantic_blocks)
install_product_card_commands(_command_router)
install_product_data_runtime(GraphicsSession, _command_router)

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
    "GraphicsCommandRouter",
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
    "PptxArtworkIssue",
    "PptxArtworkRecoveryReport",
    "PptxEffectAudit",
    "PptxEffectMappingIssue",
    "PptxEffectMappingReport",
    "PptxEffectNodeMapping",
    "PptxFidelityReport",
    "PptxFillRectContract",
    "PptxFillRectIssue",
    "PptxFillRectRecoveryReport",
    "PptxGroupReport",
    "PptxMappingAudit",
    "PptxSlideStructure",
    "PptxSpacingIssue",
    "PptxSpacingRecoveryReport",
    "PptxStructureReport",
    "PreflightIssue",
    "ProductCardCreation",
    "ProductUpdateResult",
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
    "clone_page_with_fresh_ids",
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
    "recover_pptx_artwork",
    "recover_pptx_fill_rects",
    "recover_pptx_spacing",
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
