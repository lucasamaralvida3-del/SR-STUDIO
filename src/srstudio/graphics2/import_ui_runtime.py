from __future__ import annotations

"""UI bridge for importing PowerPoint/Canva-exported PPTX files into G2.

This module does not implement a parser. It exposes the existing
``GraphicsImportService`` through the editor command router so the real Qt/QML
host can replace the live ``GraphicsSession`` document after a file picker
selection.
"""

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .id_repair import repair_legacy_cross_page_ids
from .import_bridge import GraphicsImportService


def install_import_ui_commands(command_module: Any) -> None:
    router_type = command_module.GraphicsCommandRouter
    if bool(getattr(router_type, "_sr_import_ui_installed", False)):
        return

    original_dispatch = router_type.dispatch

    def dispatch(self, command: dict[str, Any]):
        name = str(command.get("name") or "").strip().lower()
        if name != "import_pptx":
            return original_dispatch(self, command)

        raw_path = str(command.get("path") or "").strip()
        if not raw_path:
            return command_module.CommandResult(False, False, "Selecione um arquivo PowerPoint (.pptx).")

        try:
            source = _local_path(raw_path)
        except Exception as exc:
            return command_module.CommandResult(
                False,
                False,
                "Não foi possível importar este arquivo PPTX.",
                {"technical_error": f"{type(exc).__name__}: {exc}"},
            )

        if source.suffix.lower() != ".pptx":
            return command_module.CommandResult(False, False, "Selecione um arquivo PowerPoint (.pptx).")
        if not source.is_file():
            return command_module.CommandResult(
                False,
                False,
                "Não foi possível importar este arquivo PPTX.",
                {"technical_error": f"Arquivo não encontrado: {source}"},
            )

        try:
            imported = GraphicsImportService().import_file(source, project_name=source.stem)
            document = imported.document
            if not document.pages:
                raise ValueError("O importador retornou um documento sem páginas")
            document.active_page_id = document.pages[0].id

            # Promote only after the existing importer has completed successfully.
            # A failure therefore leaves the current canvas/session untouched.
            self.session.document = document
            self.session.history.clear()
            self.session.clear_selection()
            self.integrity_repair = repair_legacy_cross_page_ids(document)
            if hasattr(self, "_clipboard"):
                self._clipboard = None

            page_count = len(document.pages)
            return command_module.CommandResult(
                True,
                True,
                f"PPTX importado · {page_count} página(s).",
                {
                    "source": str(source),
                    "page_count": page_count,
                    "active_page_id": document.active_page_id,
                    "import_audit": imported.audit.to_dict(),
                },
            )
        except Exception as exc:
            return command_module.CommandResult(
                False,
                False,
                "Não foi possível importar este arquivo PPTX.",
                {"technical_error": f"{type(exc).__name__}: {exc}"},
            )

    router_type.dispatch = dispatch
    router_type._sr_import_ui_installed = True


def _local_path(raw: str) -> Path:
    text = str(raw or "").strip()
    parsed = urlparse(text)
    if parsed.scheme.lower() != "file":
        return Path(text).expanduser().resolve()

    path_text = unquote(parsed.path or "")
    netloc = unquote(parsed.netloc or "")
    if netloc and netloc.lower() not in {"", "localhost"}:
        path_text = f"//{netloc}{path_text}"
    # QML FileDialog returns file:///C:/... on Windows.
    if len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
        path_text = path_text[1:]
    return Path(path_text).expanduser().resolve()
