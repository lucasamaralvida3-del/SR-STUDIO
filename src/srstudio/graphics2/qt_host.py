from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
import copy
import json
import sys
import threading

from .autosave import AutosaveManager, RecoveryPoint, default_autosave_root
from .command_router import GraphicsCommandRouter
from .editor_persistence import (
    EditorPersistenceState,
    EditorRecoveryJournal,
    document_digest,
    newer_recovery_point,
)
from .fonts import register_qt_document_fonts
from .model import GraphicsDocument
from .operations import GraphicsSession
from .quality import ProductionGateReport, inspect_production_gate
from .qt_image_provider import PREVIEW_PROVIDER_NAME, create_live_scene_image_provider, inject_preview_image_urls

GRAPHICS_API_CHOICES = ("auto", "d3d11", "d3d12", "vulkan", "opengl", "software")
AUTOSAVE_INTERVAL_MS = 45_000


@dataclass(slots=True)
class GraphicsLaunchContext:
    document: GraphicsDocument
    source: Path | None = None
    cache_dir: Path | None = None
    gate: ProductionGateReport | None = None
    import_audit: dict[str, Any] | None = None
    saved_digest: str = ""
    recovered_from: RecoveryPoint | None = None


@dataclass(slots=True, frozen=True)
class GraphicsApiProbe:
    requested: str
    resolved: str


def qt_quick_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except Exception:
        return False
    return True


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-graphics-engine-2",
        description="SR Graphics Engine 2 — editor Qt Quick/GPU e host direto de projetos reais.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        help="PPTX/XLSX suportado pelo importador ou pacote .srscene/.zip. Sem arquivo retoma a sessão pendente.",
    )
    parser.add_argument(
        "--graphics-api",
        choices=GRAPHICS_API_CHOICES,
        default="auto",
        help="Backend do Qt Quick. 'auto' deixa o Qt escolher conforme a plataforma/GPU.",
    )
    parser.add_argument("--project-name", default="", help="Nome opcional para o projeto importado.")
    parser.add_argument(
        "--new-project",
        action="store_true",
        help="Ignora a última sessão pendente e abre um projeto vazio.",
    )
    parser.add_argument(
        "--probe-graphics-api",
        action="store_true",
        help="Inicializa uma janela mínima, informa o backend Qt Quick realmente resolvido e encerra.",
    )
    return parser


def load_launch_context(
    source: str | Path | None,
    *,
    project_name: str = "",
    resume_last: bool = True,
) -> GraphicsLaunchContext:
    if source is None:
        if resume_last:
            resumed = _resume_pending_session(project_name=project_name)
            if resumed is not None:
                return resumed
        document = GraphicsDocument(name=project_name or "Novo Projeto SR — Graphics Engine 2")
        return GraphicsLaunchContext(document=document, gate=inspect_production_gate(document))

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    if path.suffix.lower() in {".srscene", ".zip"}:
        from .package import load_package

        cache_dir = _runtime_cache_dir(path)
        saved_document = load_package(path, extract_assets_to=cache_dir / "assets")
        saved_digest = document_digest(saved_document)
        autosave_manager = AutosaveManager(default_autosave_root())
        recovery_point = newer_recovery_point(autosave_manager, saved_document, path)
        document = saved_document
        if recovery_point is not None:
            document = autosave_manager.recover(
                recovery_point,
                extract_assets_to=cache_dir / "recovery-assets",
            )
        if project_name:
            document.name = project_name
        gate = inspect_production_gate(document, require_visual_fidelity=False)
        return GraphicsLaunchContext(
            document=document,
            source=path,
            cache_dir=cache_dir,
            gate=gate,
            saved_digest=saved_digest,
            recovered_from=recovery_point,
        )

    from .import_bridge import GraphicsImportService

    imported = GraphicsImportService().import_file(path, project_name=project_name or path.stem)
    gate = inspect_production_gate(imported.document, require_visual_fidelity=False)
    return GraphicsLaunchContext(
        document=imported.document,
        source=path,
        cache_dir=None,
        gate=gate,
        import_audit=imported.audit.to_dict(),
    )


def _resume_pending_session(*, project_name: str = "") -> GraphicsLaunchContext | None:
    root = default_autosave_root()
    manager = AutosaveManager(root)
    journal = EditorRecoveryJournal(root)
    point = journal.recovery_point(manager)
    current = journal.current()
    if point is None or current is None:
        return None

    cache_dir = _runtime_cache_dir(point.path)
    document = manager.recover(point, extract_assets_to=cache_dir / "recovery-assets")
    source = current.source_path if current.source_path and current.source_path.is_file() else None
    saved_digest = _saved_package_digest(source)
    if project_name:
        document.name = project_name
    gate = inspect_production_gate(document, require_visual_fidelity=False)
    return GraphicsLaunchContext(
        document=document,
        source=source,
        cache_dir=cache_dir,
        gate=gate,
        saved_digest=saved_digest,
        recovered_from=point,
    )


def _saved_package_digest(source: Path | None) -> str:
    if source is None or source.suffix.lower() not in {".srscene", ".zip"} or not source.is_file():
        return ""
    try:
        from .package import load_package

        return document_digest(load_package(source))
    except (OSError, ValueError, KeyError):
        return ""


def build_editor_diagnostics(
    document: GraphicsDocument,
    *,
    import_audit: dict[str, Any] | None = None,
    source: str | Path | None = None,
    graphics_api: str = "auto",
) -> dict[str, Any]:
    gate = inspect_production_gate(document, require_visual_fidelity=False)
    metadata = dict(document.metadata or {})
    audit = copy.deepcopy(import_audit if import_audit is not None else metadata.get("graphics2_import_audit") or {})
    visual = copy.deepcopy(metadata.get("visual_fidelity_last") or {})
    mapping = copy.deepcopy(metadata.get("pptx_mapping_audit") or {})
    pptx_fidelity = copy.deepcopy(metadata.get("pptx_fidelity") or {})
    semantic = copy.deepcopy(metadata.get("semantic_recovery_complete") or metadata.get("semantic_blocks") or {})
    return {
        "production_gate": gate.to_dict(),
        "import_audit": audit,
        "visual_fidelity": visual,
        "pptx_mapping": mapping,
        "pptx_fidelity": pptx_fidelity,
        "semantic_recovery": semantic,
        "graphics_api_requested": _normalize_graphics_api(graphics_api),
        "source": str(source or ""),
    }


def prepare_qml_payload(scene: dict[str, Any]) -> dict[str, Any]:
    """Entrega o SR Scene ao QML sem reescrever contratos de texto."""

    return scene


def _attach_context_qml_tool(
    engine,
    root_window,
    qml_path: Path,
    *,
    QQmlComponent,
    QQuickItem,
    QQuickWindow,
    QUrl,
):
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_path.resolve())))
    if component.isError():
        details = "; ".join(error.toString() for error in component.errors())
        raise RuntimeError(f"Falha ao carregar {qml_path.name}: {details}")
    tool = component.create(engine.rootContext())
    if tool is None:
        details = "; ".join(error.toString() for error in component.errors())
        raise RuntimeError(f"Falha ao criar {qml_path.name}: {details or 'erro QML desconhecido'}")
    parent_item = root_window.contentItem() if isinstance(root_window, QQuickWindow) else None
    if parent_item is not None and isinstance(tool, QQuickItem):
        tool.setParentItem(parent_item)
    tool.setParent(root_window)
    return component, tool


def _snapshot_document(session: GraphicsSession) -> GraphicsDocument:
    return GraphicsDocument.from_dict(session.document.to_dict())


def launch_qt_quick_editor(
    document: GraphicsDocument | None = None,
    *,
    graphics_api: str = "auto",
    launch_context: GraphicsLaunchContext | None = None,
) -> int:
    try:
        from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
        from PySide6.QtQuick import QQuickItem, QQuickWindow, QSGRendererInterface
    except Exception as exc:
        raise RuntimeError("SR Graphics Engine 2 requer a dependência opcional 'graphics2' (PySide6).") from exc

    requested_api = _normalize_graphics_api(graphics_api)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("SR Graphics Engine 2")
    _set_graphics_api(requested_api, QQuickWindow, QSGRendererInterface)

    context = launch_context or GraphicsLaunchContext(document=document or GraphicsDocument())
    if document is not None and launch_context is not None and document is not launch_context.document:
        context = GraphicsLaunchContext(document=document, source=launch_context.source, cache_dir=launch_context.cache_dir)
    session = GraphicsSession(context.document)
    router = GraphicsCommandRouter(session)
    gate = context.gate or inspect_production_gate(session.document, require_visual_fidelity=False)
    preview_provider = create_live_scene_image_provider()
    autosave_root = default_autosave_root()
    autosave_manager = AutosaveManager(autosave_root)
    recovery_journal = EditorRecoveryJournal(autosave_root)
    persistence = EditorPersistenceState(
        saved_digest=str(context.saved_digest or ""),
        autosave_digest=document_digest(session.document) if context.recovered_from is not None else "",
        saved_path=(
            context.source.resolve()
            if context.saved_digest and context.source is not None and context.source.suffix.lower() in {".srscene", ".zip"}
            else None
        ),
        recovered_from=context.recovered_from,
    )

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()
        saveAsRequested = Signal()
        fileJobDone = Signal(bool, str, str, str, str)
        autosaveDone = Signal(bool, str, str, str)

        def __init__(self) -> None:
            super().__init__()
            self._status = _startup_status(context, gate, requested_api)
            self._busy = False
            self._autosave_busy = False
            self.fileJobDone.connect(self._finish_file_job)
            self.autosaveDone.connect(self._finish_autosave)

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            preview_provider.sync_document(session.document)
            payload = inject_preview_image_urls(router.payload(), session.document)
            editor = payload.setdefault("editor", {})
            editor["diagnostics"] = build_editor_diagnostics(
                session.document,
                import_audit=context.import_audit,
                source=context.source,
                graphics_api=requested_api,
            )
            editor["dirty"] = persistence.is_dirty(session.document)
            editor["autosave_busy"] = self._autosave_busy
            editor["recovered_from_autosave"] = context.recovered_from is not None
            return json.dumps(prepare_qml_payload(payload), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        @Property(bool, notify=statusChanged)
        def busy(self) -> bool:
            return self._busy

        @Property(bool, notify=sceneChanged)
        def dirty(self) -> bool:
            return persistence.is_dirty(session.document)

        @Property(bool, notify=statusChanged)
        def autosaveBusy(self) -> bool:
            return self._autosave_busy

        def _run(self, command: dict) -> None:
            result = router.dispatch(command)
            self._status = result.message or ("Concluído" if result.ok else "Falha")
            self.statusChanged.emit()
            self.sceneChanged.emit()

        def set_status(self, text: str) -> None:
            self._status = str(text)
            self.statusChanged.emit()

        def _start_file_job(
            self,
            kind: str,
            target: Path,
            task: Callable[[GraphicsDocument, Path], str],
        ) -> None:
            if self._busy:
                self._status = "Aguarde a operação de arquivo atual terminar."
                self.statusChanged.emit()
                return
            snapshot = _snapshot_document(session)
            snapshot_digest = document_digest(snapshot)
            self._busy = True
            labels = {"save": "Salvando projeto", "pdf": "Exportando PDF", "png": "Exportando PNG"}
            self._status = f"{labels.get(kind, 'Processando')} · {target.name}..."
            self.statusChanged.emit()

            def worker() -> None:
                try:
                    message = task(snapshot, target)
                    self.fileJobDone.emit(True, kind, str(target), snapshot_digest, message)
                except Exception as exc:
                    self.fileJobDone.emit(False, kind, str(target), snapshot_digest, f"{type(exc).__name__}: {exc}")

            threading.Thread(target=worker, name=f"sr-graphics2-{kind}", daemon=True).start()

        def _finish_file_job(self, ok: bool, kind: str, target: str, digest: str, message: str) -> None:
            self._busy = False
            if ok and kind == "save":
                final = Path(target).resolve()
                context.source = final
                context.saved_digest = digest
                context.recovered_from = None
                persistence.mark_saved(digest, final)
                if not persistence.is_dirty(session.document):
                    recovery_journal.clear(session.document.id)
            self._status = message if ok else f"Falha: {message}"
            self.statusChanged.emit()
            self.sceneChanged.emit()

        def _start_autosave(self, *, force: bool = False) -> None:
            if self._autosave_busy or self._busy:
                return
            snapshot = _snapshot_document(session)
            digest = document_digest(snapshot)
            if not force and not persistence.needs_autosave(snapshot):
                return
            if digest == persistence.saved_digest or digest == persistence.autosave_digest:
                return
            self._autosave_busy = True
            self.statusChanged.emit()

            def worker() -> None:
                try:
                    path = autosave_manager.save(snapshot, embed_local_assets=True)
                    self.autosaveDone.emit(True, str(path), digest, f"Autosave protegido · {path.name}")
                except Exception as exc:
                    self.autosaveDone.emit(False, "", digest, f"{type(exc).__name__}: {exc}")

            threading.Thread(target=worker, name="sr-graphics2-autosave", daemon=True).start()

        def _finish_autosave(self, ok: bool, target: str, digest: str, message: str) -> None:
            self._autosave_busy = False
            if ok:
                persistence.mark_autosaved(digest)
                recovery_journal.mark(
                    session.document.id,
                    target,
                    source_path=context.source,
                )
                self._status = message
            else:
                self._status = f"Falha no autosave: {message}"
            self.statusChanged.emit()
            self.sceneChanged.emit()

        def _save_to(self, target: Path) -> None:
            def task(snapshot: GraphicsDocument, output: Path) -> str:
                from .package import load_package, save_package

                final = save_package(snapshot, output, embed_local_assets=True)
                verified = load_package(final)
                if verified.id != snapshot.id or len(verified.pages) != len(snapshot.pages):
                    raise ValueError("Verificação pós-save não corresponde ao documento salvo")
                return f"Projeto salvo e verificado · {final.name}"

            self._start_file_job("save", target, task)

        @Slot(str)
        def selectNode(self, node_id: str) -> None:
            self._run({"name": "select", "node_id": node_id})

        @Slot(str, bool, bool)
        def selectNodeAdvanced(self, node_id: str, additive: bool, toggle: bool) -> None:
            self._run(
                {
                    "name": "select",
                    "node_id": node_id,
                    "additive": additive,
                    "toggle": toggle,
                    "semantic": True,
                    "semantic_scope": "auto",
                }
            )

        @Slot(float, float)
        def moveSelection(self, dx: float, dy: float) -> None:
            self._run({"name": "move", "dx": dx, "dy": dy, "snap": True})

        @Slot(float, float, float)
        def moveSelectionAtZoom(self, dx: float, dy: float, zoom: float) -> None:
            self._run({"name": "move", "dx": dx, "dy": dy, "snap": True, "zoom": zoom})

        @Slot()
        def undo(self) -> None:
            self._run({"name": "undo"})

        @Slot()
        def redo(self) -> None:
            self._run({"name": "redo"})

        @Slot(str, str)
        def editText(self, node_id: str, text: str) -> None:
            self._run({"name": "edit_text", "node_id": node_id, "text": text})

        @Slot(str, result=str)
        def dispatch(self, payload: str) -> str:
            result_raw = router.dispatch_json(payload)
            try:
                self._status = str(json.loads(result_raw).get("message") or "")
            except Exception:
                self._status = "Comando processado"
            self.statusChanged.emit()
            self.sceneChanged.emit()
            return result_raw

        @Slot()
        def saveProject(self) -> None:
            if persistence.saved_path is None:
                self.saveAsRequested.emit()
                return
            self._save_to(persistence.saved_path)

        @Slot(str)
        def saveSceneAs(self, raw_target: str) -> None:
            target = _qml_file_path(raw_target, ".srscene", QUrl)
            if target is None:
                return
            self._save_to(target)

        @Slot()
        def autosaveIfNeeded(self) -> None:
            self._start_autosave(force=False)

        @Slot(str)
        def exportPdf(self, raw_target: str) -> None:
            target = _qml_file_path(raw_target, ".pdf", QUrl)
            if target is None:
                return

            def task(snapshot: GraphicsDocument, output: Path) -> str:
                from .qt_renderer import render_pdf

                report = render_pdf(snapshot, output, dpi=600)
                warning = f" · {len(report.warnings)} aviso(s)" if report.warnings else ""
                return f"PDF exportado · {report.pages} página(s){warning}"

            self._start_file_job("pdf", target, task)

        @Slot(str)
        def exportPng(self, raw_target: str) -> None:
            target = _qml_file_path(raw_target, ".png", QUrl)
            if target is None:
                return
            active_id = session.document.active_page_id
            page_index = next(
                (index for index, page in enumerate(session.document.pages) if page.id == active_id),
                0,
            )

            def task(snapshot: GraphicsDocument, output: Path) -> str:
                from .qt_renderer import render_png

                report = render_png(snapshot, output, page_index=page_index, dpi=300)
                warning = f" · {len(report.warnings)} aviso(s)" if report.warnings else ""
                return f"PNG exportado · {report.width}×{report.height}px{warning}"

            self._start_file_job("png", target, task)

    font_report = register_qt_document_fonts(session.document)
    engine = QQmlApplicationEngine()
    engine.addImageProvider(PREVIEW_PROVIDER_NAME, preview_provider)
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml_dir = Path(__file__).with_name("qml")
    qml = qml_dir / "GraphicsEditor.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    roots = engine.rootObjects()
    if not roots:
        raise RuntimeError("Falha ao carregar a interface Qt Quick do SR Graphics Engine 2.")

    root_window = roots[0]
    image_component, image_inspector = _attach_context_qml_tool(
        engine,
        root_window,
        qml_dir / "ImageInspector.qml",
        QQmlComponent=QQmlComponent,
        QQuickItem=QQuickItem,
        QQuickWindow=QQuickWindow,
        QUrl=QUrl,
    )
    quality_component, quality_inspector = _attach_context_qml_tool(
        engine,
        root_window,
        qml_dir / "QualityInspector.qml",
        QQmlComponent=QQmlComponent,
        QQuickItem=QQuickItem,
        QQuickWindow=QQuickWindow,
        QUrl=QUrl,
    )
    actions_component, project_actions = _attach_context_qml_tool(
        engine,
        root_window,
        qml_dir / "ProjectActions.qml",
        QQmlComponent=QQmlComponent,
        QQuickItem=QQuickItem,
        QQuickWindow=QQuickWindow,
        QUrl=QUrl,
    )
    page_component, page_inspector = _attach_context_qml_tool(
        engine,
        root_window,
        qml_dir / "PageInspector.qml",
        QQmlComponent=QQmlComponent,
        QQuickItem=QQuickItem,
        QQuickWindow=QQuickWindow,
        QUrl=QUrl,
    )

    autosave_timer = QTimer(bridge)
    autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
    autosave_timer.timeout.connect(bridge.autosaveIfNeeded)
    autosave_timer.start()
    QTimer.singleShot(5_000, bridge.autosaveIfNeeded)

    def protect_unsaved_on_quit() -> None:
        try:
            snapshot = _snapshot_document(session)
            if persistence.needs_autosave(snapshot):
                digest = document_digest(snapshot)
                recovery_path = autosave_manager.save(snapshot, embed_local_assets=True)
                persistence.mark_autosaved(digest)
                recovery_journal.mark(
                    snapshot.id,
                    recovery_path,
                    source_path=context.source,
                )
                return
            if not persistence.is_dirty(snapshot):
                recovery_journal.clear(snapshot.id)
        except Exception as exc:
            print(f"SR Graphics Engine 2: autosave de encerramento falhou: {exc}", file=sys.stderr)

    app.aboutToQuit.connect(protect_unsaved_on_quit)

    _context_tools = (
        preview_provider,
        image_component,
        image_inspector,
        quality_component,
        quality_inspector,
        actions_component,
        project_actions,
        page_component,
        page_inspector,
        autosave_timer,
    )

    app.processEvents()
    resolved_value = _resolved_api_from_window(root_window, QQuickWindow)
    resolved_api = _graphics_api_name(resolved_value, QSGRendererInterface)
    details = [f"GPU: {resolved_api}"]
    if context.source:
        details.insert(0, context.source.name)
    if context.recovered_from is not None:
        details.append("autosave recuperado")
    live_gate = inspect_production_gate(session.document, require_visual_fidelity=False)
    details.append(f"gate {live_gate.score}/100")
    if font_report.families:
        details.append("fontes: " + ", ".join(font_report.families))
    elif font_report.warnings:
        details.append(font_report.warnings[0])
    bridge.set_status(" · ".join(details))
    return int(app.exec())


def _qml_file_path(raw: str, suffix: str, QUrl) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    url = QUrl(text)
    value = url.toLocalFile() if url.isLocalFile() else text
    if not value:
        return None
    path = Path(value).expanduser()
    if suffix and path.suffix.lower() != suffix.lower():
        path = path.with_suffix(suffix)
    return path.resolve()


def probe_graphics_api(graphics_api: str = "auto") -> GraphicsApiProbe:
    try:
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
    except Exception as exc:
        raise RuntimeError("Diagnóstico GPU requer a dependência opcional 'graphics2' (PySide6).") from exc

    requested = _normalize_graphics_api(graphics_api)
    app = QGuiApplication.instance() or QGuiApplication(["sr-graphics-engine-2-probe"])
    _set_graphics_api(requested, QQuickWindow, QSGRendererInterface)
    window = QQuickWindow()
    try:
        window.resize(64, 64)
        window.show()
        app.processEvents()
        value = window.rendererInterface().graphicsApi()
        return GraphicsApiProbe(requested=requested, resolved=_graphics_api_name(value, QSGRendererInterface))
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def _set_graphics_api(name: str, QQuickWindow, QSGRendererInterface) -> None:
    api = QSGRendererInterface.GraphicsApi
    mapping = {
        "auto": api.Unknown,
        "d3d11": api.Direct3D11,
        "d3d12": api.Direct3D12,
        "vulkan": api.Vulkan,
        "opengl": api.OpenGL,
        "software": api.Software,
    }
    QQuickWindow.setGraphicsApi(mapping[name])


def _resolved_api_from_window(root: object, QQuickWindow):
    if isinstance(root, QQuickWindow):
        try:
            return root.rendererInterface().graphicsApi()
        except Exception:
            pass
    return QQuickWindow.graphicsApi()


def _graphics_api_name(value, QSGRendererInterface) -> str:
    api = QSGRendererInterface.GraphicsApi
    labels = {
        api.Unknown: "Auto/Unknown",
        api.Software: "Software",
        api.OpenGL: "OpenGL",
        api.Direct3D11: "Direct3D 11",
        api.Direct3D12: "Direct3D 12",
        api.Vulkan: "Vulkan",
        api.Metal: "Metal",
        api.Null: "Null",
    }
    return labels.get(value, str(value))


def _normalize_graphics_api(value: str) -> str:
    name = str(value or "auto").strip().lower()
    aliases = {
        "direct3d11": "d3d11",
        "direct3d12": "d3d12",
        "d3d": "d3d11",
        "gl": "opengl",
        "default": "auto",
    }
    name = aliases.get(name, name)
    if name not in GRAPHICS_API_CHOICES:
        raise ValueError(f"Backend gráfico inválido: {value}. Opções: {', '.join(GRAPHICS_API_CHOICES)}")
    return name


def _runtime_cache_dir(source: Path) -> Path:
    stat = source.stat()
    identity = f"{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    digest = sha256(identity).hexdigest()[:20]
    root = Path.home() / ".srstudio5" / "runtime-g2" / digest
    root.mkdir(parents=True, exist_ok=True)
    return root


def _startup_status(context: GraphicsLaunchContext, gate: ProductionGateReport, requested_api: str) -> str:
    source = context.source.name if context.source else "Novo projeto"
    requested = "automático" if requested_api == "auto" else requested_api
    state = "pronto" if gate.ready else "em validação"
    recovery = " · recovery autosave" if context.recovered_from is not None else ""
    return f"{source} · {state} · gate {gate.score}/100 · GPU {requested}{recovery}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.probe_graphics_api:
            probe = probe_graphics_api(args.graphics_api)
            print(f"SR Graphics Engine 2 GPU: solicitado={probe.requested} | resolvido={probe.resolved}")
            return 0
        context = load_launch_context(
            args.source,
            project_name=args.project_name,
            resume_last=not args.new_project,
        )
        return launch_qt_quick_editor(
            context.document,
            graphics_api=args.graphics_api,
            launch_context=context,
        )
    except Exception as exc:
        print(f"SR Graphics Engine 2: ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
