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
from . import qt_renderer as _qt_renderer
from .qt_render_runtime import ensure_qt_gui_application, install_headless_renderer_guard
from .scene_fingerprint import PageFingerprint, SceneFingerprint, fingerprint_document, store_scene_fingerprint
from . import semantic_blocks as _semantic_blocks
from .semantic_blocks import (
    SemanticBlock,
    SemanticBlockReport,
    semantic_block,
    semantic_member_ids,
    semantic_owner,
)
from .semantic_runtime import install_semantic_recovery_guard

# A proteção precisa ser instalada antes de importadores/recuperadores posteriores
# capturarem uma referência local ao builder semântico histórico.
install_semantic_recovery_guard(_semantic_blocks)
build_semantic_blocks = _semantic_blocks.build_semantic_blocks

# O bridge histórico protege todos os nodes fora de SmartSlots. Para o Studio de
# Encartes profissional, textos e imagens importados precisam permanecer
# editáveis sem liberar as formas estruturais do template. O binder também usa
# o texto original do template para preservar moeda/unidade em caixas separadas.
from . import import_bridge as _import_bridge
from .binding_runtime import install_template_aware_binding_guard
from .import_edit_runtime import apply_import_editability, install_import_editability_guard

install_import_editability_guard(_import_bridge)
install_template_aware_binding_guard(_import_bridge)

from . import command_router as _command_router
from .image_replace_runtime import install_image_replace_command
from .product_card_runtime import (
    ProductCardCreation,
    install_product_card_commands,
    install_product_card_runtime,
)

# ProductCard/SmartSlot é um contrato de backend. O QML pode chamá-lo pelo
# command router sem conhecer IDs/roles internos, e os mesmos métodos ficam
# disponíveis para testes, automações e SR IA.
install_product_card_runtime(GraphicsSession, _semantic_blocks)
install_image_replace_command(_command_router)
install_product_card_commands(_command_router)

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
ENGINE_VERSION = "2.0.0-alpha.43"
SCHEMA_VERSION = "srscene/2.0"

# Mantém a API GraphicsSession.add_page existente, porém endurece a duplicação
# para projetos multipágina com identidades únicas e referências remapeadas.
install_safe_page_duplication(GraphicsSession)

# Exportadores também são usados por CLI, testes e automações, onde não existe
# necessariamente uma QGuiApplication criada pelo editor Qt Quick.
install_headless_renderer_guard(_qt_renderer)
RenderReport = _qt_renderer.RenderReport
render_png = _qt_renderer.render_png
render_pdf = _qt_renderer.render_pdf
GraphicsCommandRouter = _command_router.GraphicsCommandRouter

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
    "apply_import_editability",
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
    "ensure_qt_gui_application",
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
