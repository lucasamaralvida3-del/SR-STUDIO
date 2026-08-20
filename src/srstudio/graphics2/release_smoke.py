from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys

import srstudio

from . import ENGINE_VERSION
from .model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from .package import load_package, save_package
from .qt_host import launch_qt_quick_editor, probe_graphics_api
from .qt_renderer import render_pdf, render_png


def build_smoke_document() -> GraphicsDocument:
    document = GraphicsDocument(name="SR Graphics Engine 2 Release Smoke")
    page = document.active_page
    page.width = 640
    page.height = 480
    page.background = "#FFFFFF"
    page.add_node(
        GraphicsNode(
            kind=NodeKind.RECT,
            name="Release Smoke Card",
            transform=Transform(x=64, y=64, width=512, height=352),
            style={"fill": "#F4F4F4", "stroke": "#222222", "stroke_width": 2},
        )
    )
    page.add_node(
        GraphicsNode(
            kind=NodeKind.TEXT,
            name="Release Smoke Text",
            transform=Transform(x=96, y=160, width=448, height=120),
            text="SR STUDIO G2 RELEASE SMOKE",
            style={"font_family": "Arial", "font_size": 28, "color": "#111111", "align": "center"},
            z_index=1,
        )
    )
    return document


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_release_smoke(output_dir: str | Path) -> dict[str, object]:
    try:
        import PySide6
        from PySide6.QtCore import QLibraryInfo, QTimer
        from PySide6.QtGui import QGuiApplication
    except Exception as exc:
        raise RuntimeError(
            "Release smoke não conseguiu carregar o runtime PySide6/Qt: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(["sr-graphics2-release-smoke"])
    app.setApplicationName("SR Graphics Engine 2 Release Smoke")

    qml_dir = Path(__file__).with_name("qml")
    required_qml = [
        "GraphicsEditor.qml",
        "ImageInspector.qml",
        "PageInspector.qml",
        "ProjectActions.qml",
        "QualityInspector.qml",
        "SceneImage.qml",
    ]
    missing_qml = [name for name in required_qml if not (qml_dir / name).is_file()]
    if missing_qml:
        raise RuntimeError("QML obrigatório ausente: " + ", ".join(missing_qml))

    probe = probe_graphics_api("software")
    document = build_smoke_document()
    project_path = save_package(document, root / "release-smoke.srscene", embed_local_assets=True)
    reopened = load_package(project_path, extract_assets_to=root / "assets")
    if reopened.name != document.name or len(reopened.pages) != 1:
        raise RuntimeError("Round-trip SR Scene divergiu no release smoke.")

    png = render_png(reopened, root / "release-smoke.png", dpi=96)
    pdf = render_pdf(reopened, root / "release-smoke.pdf", dpi=144)
    if not png.ok or not pdf.ok:
        raise RuntimeError("Exportação do release smoke não gerou artefatos válidos.")

    plugin_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    qml_import_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath))
    if not plugin_path.is_dir():
        raise RuntimeError(f"Diretório de plugins Qt ausente: {plugin_path}")
    if not qml_import_path.is_dir():
        raise RuntimeError(f"Diretório de imports QML ausente: {qml_import_path}")

    # Este é o gate que transforma "arquivos QML existem" em "o editor real
    # carregou". O load do GraphicsEditor e das ferramentas contextuais ocorre
    # sincronamente dentro de launch_qt_quick_editor; o timer apenas fecha o
    # event loop logo depois, para manter o smoke não interativo.
    os.environ["SR_STUDIO_G2_AUTOSAVE_ROOT"] = str(root / "autosave")
    QTimer.singleShot(750, app.quit)
    editor_exit_code = launch_qt_quick_editor(reopened, graphics_api="software")
    if editor_exit_code != 0:
        raise RuntimeError(f"Editor Qt Quick encerrou o release smoke com código {editor_exit_code}.")

    artifacts = {}
    for path in (project_path, png.output, pdf.output):
        artifacts[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }

    result: dict[str, object] = {
        "schema": "srstudio/g2-release-smoke-2",
        "ok": True,
        "srstudio_version": srstudio.__version__,
        "graphics2_version": ENGINE_VERSION,
        "python": sys.version.split()[0],
        "pyside6": str(PySide6.__version__),
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "graphics_api_requested": probe.requested,
        "graphics_api_resolved": probe.resolved,
        "editor_qml_startup": True,
        "editor_exit_code": editor_exit_code,
        "qml_dir": str(qml_dir.resolve()),
        "qt_plugins": str(plugin_path.resolve()),
        "qt_qml_imports": str(qml_import_path.resolve()),
        "artifacts": artifacts,
        "jpeg_export": "delegated-to-chat6-not-required-by-baseline-smoke",
    }
    report_path = root / "release-smoke.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="sr-graphics2-release-smoke")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_release_smoke(args.output_dir)
    except Exception as exc:
        print(f"SR Graphics2 release smoke: ERRO: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
