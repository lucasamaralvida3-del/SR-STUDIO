from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import sys

from .command_router import GraphicsCommandRouter
from .fonts import register_qt_document_fonts
from .model import GraphicsDocument
from .operations import GraphicsSession
from .quality import ProductionGateReport, inspect_production_gate

GRAPHICS_API_CHOICES = ("auto", "d3d11", "d3d12", "vulkan", "opengl", "software")


@dataclass(slots=True)
class GraphicsLaunchContext:
    document: GraphicsDocument
    source: Path | None = None
    cache_dir: Path | None = None
    gate: ProductionGateReport | None = None
    import_audit: dict[str, Any] | None = None


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
        help="PPTX/XLSX suportado pelo importador ou pacote .srscene/.zip. Sem arquivo abre projeto vazio.",
    )
    parser.add_argument(
        "--graphics-api",
        choices=GRAPHICS_API_CHOICES,
        default="auto",
        help="Backend do Qt Quick. 'auto' deixa o Qt escolher conforme a plataforma/GPU.",
    )
    parser.add_argument("--project-name", default="", help="Nome opcional para o projeto importado.")
    parser.add_argument(
        "--probe-graphics-api",
        action="store_true",
        help="Inicializa uma janela mínima, informa o backend Qt Quick realmente resolvido e encerra.",
    )
    return parser


def load_launch_context(source: str | Path | None, *, project_name: str = "") -> GraphicsLaunchContext:
    if source is None:
        document = GraphicsDocument(name=project_name or "Novo Projeto SR — Graphics Engine 2")
        return GraphicsLaunchContext(document=document, gate=inspect_production_gate(document))

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    if path.suffix.lower() in {".srscene", ".zip"}:
        from .package import load_package

        cache_dir = _runtime_cache_dir(path)
        document = load_package(path, extract_assets_to=cache_dir / "assets")
        if project_name:
            document.name = project_name
        gate = inspect_production_gate(document, require_visual_fidelity=False)
        return GraphicsLaunchContext(document=document, source=path, cache_dir=cache_dir, gate=gate)

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


def launch_qt_quick_editor(
    document: GraphicsDocument | None = None,
    *,
    graphics_api: str = "auto",
    launch_context: GraphicsLaunchContext | None = None,
) -> int:
    try:
        from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
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

    class SceneBridge(QObject):
        sceneChanged = Signal()
        statusChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._status = _startup_status(context, gate, requested_api)

        @Property(str, notify=sceneChanged)
        def sceneJson(self) -> str:
            return json.dumps(router.payload(), ensure_ascii=False, separators=(",", ":"))

        @Property(str, notify=statusChanged)
        def status(self) -> str:
            return self._status

        def _run(self, command: dict) -> None:
            result = router.dispatch(command)
            self._status = result.message or ("Concluído" if result.ok else "Falha")
            self.statusChanged.emit()
            self.sceneChanged.emit()

        def set_status(self, text: str) -> None:
            self._status = str(text)
            self.statusChanged.emit()

        @Slot(str)
        def selectNode(self, node_id: str) -> None:
            # Seleção exata continua disponível para inspector/ações internas.
            self._run({"name": "select", "node_id": node_id})

        @Slot(str, bool, bool)
        def selectNodeAdvanced(self, node_id: str, additive: bool, toggle: bool) -> None:
            # O canvas e a lista de camadas usam a seleção avançada. Quando o
            # node pertence a um PriceBlock, R$ + reais + centavos + KG/UN
            # entram juntos na seleção e não podem mais se separar ao arrastar.
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

    font_report = register_qt_document_fonts(session.document)
    engine = QQmlApplicationEngine()
    bridge = SceneBridge()
    engine.rootContext().setContextProperty("sceneBridge", bridge)
    qml = Path(__file__).with_name("qml") / "GraphicsEditor.qml"
    engine.load(QUrl.fromLocalFile(str(qml.resolve())))
    roots = engine.rootObjects()
    if not roots:
        raise RuntimeError("Falha ao carregar a interface Qt Quick do SR Graphics Engine 2.")

    app.processEvents()
    resolved_value = _resolved_api_from_window(roots[0], QQuickWindow)
    resolved_api = _graphics_api_name(resolved_value, QSGRendererInterface)
    details = [f"GPU: {resolved_api}"]
    if context.source:
        details.insert(0, context.source.name)
    details.append(f"gate {gate.score}/100")
    if font_report.families:
        details.append("fontes: " + ", ".join(font_report.families))
    elif font_report.warnings:
        details.append(font_report.warnings[0])
    bridge.set_status(" · ".join(details))
    return int(app.exec())


def probe_graphics_api(graphics_api: str = "auto") -> GraphicsApiProbe:
    """Verifica o backend que o Qt Quick realmente resolve neste computador."""

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
    return f"{source} · {state} · gate {gate.score}/100 · GPU {requested}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.probe_graphics_api:
            probe = probe_graphics_api(args.graphics_api)
            print(f"SR Graphics Engine 2 GPU: solicitado={probe.requested} | resolvido={probe.resolved}")
            return 0
        context = load_launch_context(args.source, project_name=args.project_name)
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
