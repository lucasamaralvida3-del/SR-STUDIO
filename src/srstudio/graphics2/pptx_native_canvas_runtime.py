from __future__ import annotations

"""Install the Canva native-canvas contract at the G2 import seam.

The shared importer remains authoritative for PPTX parsing.  G2 adjusts only its
own SR Scene 2 coordinate space, after the current StudioProject has been built
and before Graphics2 fidelity/artwork/group enrichment begins.
"""

from copy import deepcopy
from pathlib import Path

from .pptx_native_canvas import PptxCanvasResolution, resolve_pptx_native_canvas


def install_pptx_native_canvas_guard(import_bridge_module) -> None:
    current = import_bridge_module.from_imported_project
    if bool(getattr(current, "_g2_native_canvas_guard", False)):
        return

    def guarded(project):
        source_text = str(project.settings.get("pptx_source") or "").strip()
        resolution = None
        if source_text:
            source = Path(source_text)
            if source.suffix.lower() == ".pptx":
                resolution = resolve_pptx_native_canvas(source)
                _store_legacy_bridge_metadata(project, resolution)

        document = current(project)
        if resolution is not None:
            apply_pptx_native_canvas(document, resolution)
        return document

    guarded._g2_native_canvas_guard = True
    guarded._g2_native_canvas_original = current
    import_bridge_module.from_imported_project = guarded


def apply_pptx_native_canvas(document, resolution: PptxCanvasResolution) -> bool:
    """Store provenance and, when safe, map SR Scene 2 to intended coordinates."""

    metadata = resolution.to_metadata()
    document.metadata["pptx_canvas"] = deepcopy(metadata)
    # Compatibility with the semantic keys introduced by the historical branch.
    document.metadata["pptx_physical_page_size"] = deepcopy(metadata["pptx_physical_page_size"])
    document.metadata["intended_canvas_size"] = deepcopy(metadata["intended_canvas_size"])
    document.metadata["pptx_canvas_size_source"] = metadata["source"]
    document.metadata["pptx_canvas_size_preset"] = metadata["preset"]
    document.metadata["pptx_canvas_size_evidence"] = deepcopy(metadata["origin_evidence"])
    document.metadata["pptx_source_profile"] = deepcopy(metadata["source_profile"])

    intended = resolution.intended_canvas_size
    changed = False
    for page in document.pages:
        page.metadata["pptx_canvas"] = deepcopy(metadata)
        page.metadata["pptx_physical_page_size"] = deepcopy(metadata["pptx_physical_page_size"])
        page.metadata["intended_canvas_size"] = deepcopy(metadata["intended_canvas_size"])
        page.metadata["pptx_canvas_size_preset"] = metadata["preset"]
        page.metadata["pptx_canvas_size_source"] = metadata["source"]
        page.metadata["pptx_canvas_size_evidence"] = deepcopy(metadata["origin_evidence"])
        page.metadata["pptx_source_profile"] = deepcopy(metadata["source_profile"])

        if not resolution.uses_intended_canvas_size or intended is None:
            continue
        old_width = float(page.width)
        old_height = float(page.height)
        if old_width <= 0.0 or old_height <= 0.0:
            continue
        sx = intended.width / old_width
        sy = intended.height / old_height
        if abs(sx - 1.0) > 1e-12 or abs(sy - 1.0) > 1e-12:
            for node in page.nodes.values():
                node.transform.x *= sx
                node.transform.width *= sx
                node.transform.y *= sy
                node.transform.height *= sy
            page.guides_x = [value * sx for value in page.guides_x]
            page.guides_y = [value * sy for value in page.guides_y]
            changed = True
        page.width = intended.width
        page.height = intended.height

    document.metadata["pptx_canvas_semantic_override_applied"] = bool(
        resolution.uses_intended_canvas_size
    )
    return changed


def _store_legacy_bridge_metadata(project, resolution: PptxCanvasResolution) -> None:
    """Expose the old branch's metadata contract without changing legacy geometry."""

    metadata = resolution.to_metadata()
    project.settings["pptx_physical_page_size"] = deepcopy(metadata["pptx_physical_page_size"])
    project.settings["intended_canvas_size"] = deepcopy(metadata["intended_canvas_size"])
    project.settings["pptx_canvas_size_source"] = metadata["source"]
    project.settings["pptx_canvas_size_preset"] = metadata["preset"]
    project.settings["pptx_canvas_size_evidence"] = deepcopy(metadata["origin_evidence"])
    project.settings["pptx_source_profile"] = deepcopy(metadata["source_profile"])
