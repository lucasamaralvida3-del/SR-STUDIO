from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import srstudio
from srstudio.graphics2.import_bridge import GraphicsImportService
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity
from srstudio.graphics2.qt_renderer import render_pdf, render_png

T = TypeVar("T")

PPTX_NAMES = (
    "ATACADO.pptx",
    "CARTAZ_VENDA.pptx",
    "CLUBE_EXCLUSIVO.pptx",
    "SEGUNDA_DA_LIMPEZA.pptx",
    "SEGUNDA_DA_LIMPEZA_2.pptx",
    "SEGUNDA_DA_LIMPEZA_3.pptx",
    "SEGUNDA_DA_LIMPEZA_4.pptx",
)


def _rss_mb() -> float | None:
    status = Path("/proc/self/status")
    if not status.is_file():
        return None
    for line in status.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[1]) / 1024.0
    return None


def _pptx_root() -> Path:
    return Path(srstudio.__file__).resolve().parent / "assets" / "poster_templates" / "legacy" / "models"


def _measure(call: Callable[[], T], *, repeats: int = 1) -> tuple[T, dict[str, float | int | None]]:
    wall: list[float] = []
    cpu: list[float] = []
    rss_before = _rss_mb()
    result: T | None = None
    for _ in range(repeats):
        wall_start = time.perf_counter()
        cpu_start = time.process_time()
        result = call()
        cpu.append(time.process_time() - cpu_start)
        wall.append(time.perf_counter() - wall_start)
    gc.collect()
    rss_after = _rss_mb()
    assert result is not None
    return result, {
        "repeats": repeats,
        "min_s": min(wall),
        "median_s": statistics.median(wall),
        "max_s": max(wall),
        "cpu_median_s": statistics.median(cpu),
        "cpu_max_s": max(cpu),
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": None if rss_before is None or rss_after is None else rss_after - rss_before,
    }


def _qgui_application():
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def collect(output: Path) -> dict:
    root = _pptx_root()
    report: dict = {
        "schema": "srstudio/g2-qa-pptx-baseline/1",
        "python": os.sys.version,
        "platform": os.sys.platform,
        "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "root": str(root),
        "cases": {},
    }
    imported_documents: dict[str, object] = {}

    for name in PPTX_NAMES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Template PPTX esperado não encontrado: {path}")

        result, timing = _measure(lambda p=path: GraphicsImportService().import_file(p), repeats=2)
        document = result.document
        assert_document_integrity(document)
        pages = len(document.pages)
        nodes = sum(len(page.nodes) for page in document.pages)
        assets = len(document.assets)
        timing["seconds_per_page"] = None if pages == 0 else timing["median_s"] / pages
        report["cases"][name] = {
            "file_bytes": path.stat().st_size,
            "pages": pages,
            "nodes": nodes,
            "assets": assets,
            "warnings": list(result.warnings),
            "warning_count": len(result.warnings),
            "import": timing,
        }
        imported_documents[name] = document

    representative_name = max(
        PPTX_NAMES,
        key=lambda name: (
            report["cases"][name]["pages"],
            report["cases"][name]["nodes"],
            report["cases"][name]["file_bytes"],
        ),
    )
    representative = imported_documents[representative_name]
    report["representative"] = {"name": representative_name}

    with tempfile.TemporaryDirectory(prefix="srstudio-g2-pptx-qa-") as temp_raw:
        temp = Path(temp_raw)
        project_path = temp / "imported.srscene"
        _, report["representative"]["save"] = _measure(
            lambda: save_package(representative, project_path, embed_local_assets=True),
            repeats=3,
        )
        reopened, report["representative"]["load"] = _measure(
            lambda: load_package(project_path, extract_assets_to=temp / "assets"),
            repeats=3,
        )
        assert_document_integrity(reopened)
        report["representative"]["project_bytes"] = project_path.stat().st_size
        report["representative"]["pages"] = len(reopened.pages)
        report["representative"]["nodes"] = sum(len(page.nodes) for page in reopened.pages)
        report["representative"]["assets"] = len(reopened.assets)

        _app = _qgui_application()
        png_path = temp / "imported.png"
        png_report, report["representative"]["render_png"] = _measure(
            lambda: render_png(reopened, png_path, page_index=0, dpi=96, target_width=1080),
            repeats=3,
        )
        report["representative"]["png_bytes"] = png_report.output.stat().st_size
        report["representative"]["png_warnings"] = list(png_report.warnings)

        pdf_path = temp / "imported.pdf"
        pdf_report, report["representative"]["render_pdf"] = _measure(
            lambda: render_pdf(reopened, pdf_path, dpi=96),
            repeats=2,
        )
        report["representative"]["pdf_bytes"] = pdf_report.output.stat().st_size
        report["representative"]["pdf_pages"] = pdf_report.pages
        report["representative"]["pdf_warnings"] = list(pdf_report.warnings)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Baseline real de importação PPTX -> SR Scene 2.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/g2-qa-pptx-baseline.json"))
    args = parser.parse_args()
    report = collect(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
