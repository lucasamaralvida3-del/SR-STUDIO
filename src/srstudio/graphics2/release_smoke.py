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
from .export_output import export_jpeg, export_pdf, export_png
from .model import GraphicsDocument, GraphicsNode, NodeKind, Transform
from .package import load_package, save_package
from .qt_host import launch_qt_quick_editor, load_launch_context, probe_graphics_api


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


def _artifact(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"Artefato do frozen smoke ausente ou vazio: {path}")
    return {"bytes": path.stat().st_size, "sha256": _sha256_file(path)}


def _packaged_real_pptx() -> Path:
    path = (
        Path(srstudio.__file__).resolve().parent
        / "assets"
        / "poster_templates"
        / "legacy"
        / "models"
        / "ATACADO.pptx"
    )
    if not path.is_file() or path.stat().st_size <= 0:
        raise RuntimeError(f"PPTX real empacotado ausente: {path}")
    return path


def _run_real_pptx_gate(root: Path) -> dict[str, object]:
    pptx = _packaged_real_pptx()
    context = load_launch_context(pptx, project_name="Frozen Real PPTX Smoke")
    document = context.document
    node_count = sum(len(page.nodes) for page in document.pages)
    if not document.pages or node_count <= 0:
        raise RuntimeError("Importação do PPTX real pelo frozen runtime não produziu conteúdo editável.")
    if not isinstance(context.import_audit, dict) or not context.import_audit:
        raise RuntimeError("Importação do PPTX real pelo frozen runtime não produziu import audit.")
    scene = save_package(document, root / "real-pptx-import.srscene", embed_local_assets=True)
    return {
        "ok": True,
        "source": pptx.name,
        "source_bytes": pptx.stat().st_size,
        "pages": len(document.pages),
        "nodes": node_count,
        "import_audit": True,
        "scene": scene.name,
        "scene_bytes": scene.stat().st_size,
    }


def _run_image_db_gate(root: Path) -> dict[str, object]:
    # A fixture é criada durante o smoke para provar persistência/index/lookup sem
    # distribuir corpus privado. O algoritmo de matching não é alterado aqui.
    from PIL import Image

    from srstudio.images.lookup import ProductImageLookupService
    from srstudio.images.safe_library import SafeImageLibrary

    fixtures = root / "image-db-fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    rows = (
        ("cafe-500.png", (210, 40, 35), "CAFE VASCONCELOS SKU111 500G"),
        ("cafe-1kg.png", (35, 95, 205), "CAFE VASCONCELOS SKU222 1KG"),
        ("leite-1l.png", (235, 235, 225), "LEITE TRIANGULO SKU333 1L"),
    )
    library = SafeImageLibrary(root / "image-db")
    imported = []
    for filename, rgb, product_name in rows:
        source = fixtures / filename
        Image.new("RGB", (96, 96), rgb).save(source, "PNG")
        imported.append(
            library.import_image(
                source,
                product_name=product_name,
                kind="product",
                confidence=0.99,
                review_status="accepted",
                preferred=True,
                source_kind="frozen-smoke",
            )
        )

    # Instanciar um segundo objeto força a carga do index.json persistido em vez
    # de reutilizar somente estado em memória.
    reloaded = SafeImageLibrary(library.root)
    service = ProductImageLookupService(reloaded)
    exact = service.find_image("CAFE VASCONCELOS SKU111 500G")
    fuzzy = service.find_image("CAFE VASCONCELO SKU111 500G")
    no_match = service.find_image("PRODUTO TOTALMENTE INEXISTENTE 750ML")
    protected_other = service.find_image("CAFE VASCONCELOS SKU222 1KG")

    first_id = imported[0].id
    second_id = imported[1].id
    if exact.best_match is None or exact.best_match.asset.id != first_id or not exact.match_type.startswith("exact"):
        raise RuntimeError("Image DB frozen: find_image exact não preservou o produto esperado.")
    if fuzzy.best_match is None or fuzzy.best_match.asset.id != first_id or fuzzy.match_type != "fuzzy":
        raise RuntimeError("Image DB frozen: find_image fuzzy não preservou SKU/gramagem do produto esperado.")
    if no_match.best_match is not None:
        raise RuntimeError("Image DB frozen: produto sem match retornou imagem indevida.")
    if protected_other.best_match is None or protected_other.best_match.asset.id != second_id:
        raise RuntimeError("Image DB frozen: identidade SKU/gramagem concorrente foi trocada.")
    if fuzzy.best_match.asset.id == second_id or protected_other.best_match.asset.id == first_id:
        raise RuntimeError("Image DB frozen: proteção de SKU/gramagem falhou entre variantes concorrentes.")
    if not reloaded.index_path.is_file() or reloaded.index_path.stat().st_size <= 0:
        raise RuntimeError("Image DB frozen: index persistido ausente ou vazio.")

    return {
        "ok": True,
        "index": reloaded.index_path.name,
        "index_bytes": reloaded.index_path.stat().st_size,
        "assets": len(reloaded.all(status="accepted")),
        "exact": exact.match_type,
        "exact_confidence": exact.confidence,
        "fuzzy": fuzzy.match_type,
        "fuzzy_confidence": fuzzy.confidence,
        "no_match": no_match.best_match is None,
        "sku_grammage_protected": True,
    }


def run_release_smoke(output_dir: str | Path) -> dict[str, object]:
    try:
        import PySide6
        from PySide6.QtCore import QLibraryInfo, QTimer
        from PySide6.QtGui import QGuiApplication, QImageReader
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

    png = export_png(reopened, root / "release-smoke.png", dpi=96, target_width=640)
    jpeg = export_jpeg(reopened, root / "release-smoke.jpg", dpi=96, target_width=640, quality=92)
    pdf = export_pdf(reopened, root / "release-smoke.pdf", dpi=144)
    if not png.ok or not jpeg.ok or not pdf.ok:
        raise RuntimeError("Exportação do release smoke não gerou todos os artefatos válidos.")
    if (jpeg.width, jpeg.height) != (640, 480):
        raise RuntimeError(f"JPEG frozen smoke com dimensões inesperadas: {jpeg.width}x{jpeg.height}")
    reader = QImageReader(str(jpeg.output))
    decoded = reader.read()
    if decoded.isNull() or decoded.width() != 640 or decoded.height() != 480:
        raise RuntimeError(
            f"JPEG frozen smoke não decodificou em 640x480: {reader.errorString()}"
        )

    real_pptx = _run_real_pptx_gate(root)
    image_db = _run_image_db_gate(root)

    plugin_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    qml_import_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.QmlImportsPath))
    if not plugin_path.is_dir():
        raise RuntimeError(f"Diretório de plugins Qt ausente: {plugin_path}")
    if not qml_import_path.is_dir():
        raise RuntimeError(f"Diretório de imports QML ausente: {qml_import_path}")

    # Este gate carrega o GraphicsEditor.qml real. O timer apenas fecha o event
    # loop depois do startup para manter o smoke não interativo.
    os.environ["SR_STUDIO_G2_AUTOSAVE_ROOT"] = str(root / "autosave")
    QTimer.singleShot(750, app.quit)
    editor_exit_code = launch_qt_quick_editor(reopened, graphics_api="software")
    if editor_exit_code != 0:
        raise RuntimeError(f"Editor Qt Quick encerrou o release smoke com código {editor_exit_code}.")

    artifacts = {}
    for path in (project_path, png.output, jpeg.output, pdf.output, root / "real-pptx-import.srscene"):
        artifacts[path.name] = _artifact(path)

    result: dict[str, object] = {
        "schema": "srstudio/g2-release-smoke-3",
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
        "frozen_gates": {
            "real_pptx": real_pptx,
            "image_db": image_db,
            "save_load": {"ok": True, "project": project_path.name},
            "png": {"ok": True, "width": png.width, "height": png.height},
            "jpeg": {"ok": True, "width": jpeg.width, "height": jpeg.height, "decoded": True},
            "pdf": {"ok": True, "pages": pdf.pages},
        },
        "artifacts": artifacts,
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