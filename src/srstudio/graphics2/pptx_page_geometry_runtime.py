from __future__ import annotations

"""Runtime hook that applies G2-only PPTX page semantics before enrichment."""

from pathlib import Path

from .pptx_source_profile import apply_pptx_page_geometry, inspect_pptx_source_profile


def install_pptx_page_geometry_guard(import_bridge_module) -> None:
    """Wrap ``from_imported_project`` without touching the shared PPTX importer.

    ``GraphicsImportService.import_file`` first runs the mature shared importer,
    then calls ``from_imported_project`` and only afterwards starts G2-specific
    fidelity/crop/group passes.  Installing the geometry contract at that seam
    means every later G2 pass sees the intended canvas while the legacy
    ``StudioProject`` and its physical-ratio geometry remain untouched.
    """

    current = import_bridge_module.from_imported_project
    if bool(getattr(current, "_g2_page_geometry_guard", False)):
        return

    def guarded(project):
        document = current(project)
        source_text = str(project.settings.get("pptx_source") or "").strip()
        if source_text:
            source = Path(source_text)
            if source.suffix.lower() == ".pptx":
                profile = inspect_pptx_source_profile(source)
                apply_pptx_page_geometry(document, profile)
        return document

    guarded._g2_page_geometry_guard = True
    guarded._g2_page_geometry_original = current
    import_bridge_module.from_imported_project = guarded
