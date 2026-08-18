from __future__ import annotations

"""Entrypoint de produção do editor G2.

Mantém recovery e "último projeto salvo" como conceitos separados sem aumentar a
responsabilidade do host Qt. A ordem de abertura pelo atalho é:

1. source explícito informado pelo usuário;
2. recovery pendente (deixado para ``qt_host.load_launch_context``);
3. último `.srscene` salvo/aberto com sucesso;
4. projeto novo.
"""

from pathlib import Path
from threading import current_thread
from typing import Sequence
import sys

from . import package as package_module
from . import qt_host
from .autosave import default_autosave_root
from .editor_persistence import EditorRecentProject, EditorRecoveryJournal


def resolve_startup_args(argv: Sequence[str]) -> list[str]:
    args = [str(value) for value in argv]
    parsed = qt_host.build_parser().parse_args(args)
    if parsed.new_project or parsed.probe_graphics_api or parsed.source is not None:
        return args

    root = default_autosave_root()
    if EditorRecoveryJournal(root).current() is not None:
        # O host já sabe validar/reabrir exatamente o recovery pendente.
        return args

    recent = EditorRecentProject(root).current()
    if recent is None:
        return args
    return [str(recent.path), *args]


def install_manual_save_recent_project_hook() -> None:
    current = package_module.load_package
    if bool(getattr(current, "_sr_recent_project_hook", False)):
        return

    original = current

    def load_package(path, *, extract_assets_to=None):
        document = original(path, extract_assets_to=extract_assets_to)
        # O host reabre o arquivo no thread `sr-graphics2-save` somente depois
        # de `save_package` concluir. Marcar aqui significa que o arquivo só
        # vira "último projeto salvo" após a verificação pós-save passar.
        # O AutosaveManager já capturou sua própria referência histórica ao
        # loader antes deste hook, logo recoveries não viram projetos recentes.
        if current_thread().name == "sr-graphics2-save":
            EditorRecentProject(default_autosave_root()).mark(path, document_id=document.id)
        return document

    load_package._sr_recent_project_hook = True  # type: ignore[attr-defined]
    package_module.load_package = load_package


def remember_explicit_saved_project(argv: Sequence[str]) -> None:
    """Lembra `.srscene` aberto explicitamente, mesmo que o usuário não o resalve."""

    try:
        parsed = qt_host.build_parser().parse_args([str(value) for value in argv])
        source = Path(parsed.source).expanduser().resolve() if parsed.source is not None else None
        if source is None or source.suffix.lower() not in {".srscene", ".zip"} or not source.is_file():
            return
        document = package_module.load_package(source)
        EditorRecentProject(default_autosave_root()).mark(source, document_id=document.id)
    except (OSError, ValueError, KeyError):
        # O host apresentará o erro correto se o source explícito for inválido.
        return


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    install_manual_save_recent_project_hook()
    resolved = resolve_startup_args(raw_args)
    remember_explicit_saved_project(resolved)
    return qt_host.main(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
