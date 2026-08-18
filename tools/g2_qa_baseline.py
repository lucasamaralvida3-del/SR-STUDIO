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

from srstudio.graphics2.model import GraphicsDocument, GraphicsNode, GraphicsPage, NodeKind, Transform
from srstudio.graphics2.package import load_package, save_package
from srstudio.graphics2.preflight import assert_document_integrity
from srstudio.graphics2.qt_renderer import render_pdf, render_png

T = TypeVar("T")


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


def _page(index: int, *, nodes_per_page: int) -> GraphicsPage:
    page = GraphicsPage(name=f"Baseline {index + 1}", width=1080, height=1350)
    for node_index in range(nodes_per_page):
        column = node_index % 5
        row = node_index // 5
        kind = NodeKind.TEXT if node_index % 3 else NodeKind.RECT
        page.add_node(
            GraphicsNode(
                kind=kind,
                name=f"N{index + 1}-{node_index + 1}",
                text=f"PRODUTO QA {index + 1}-{node_index + 1}" if kind is NodeKind.TEXT else "",
                transform=Transform(
                    x=25 + column * 205,
                    y=35 + row * 100,
                    width=180,
                    height=65,
                ),
                style={
                    "font_family": "Arial",
                    "font_size": 18,
                    "font_size_unit": "px",
                    "color": "#111111",
                    "fill": "#E5E7EB",
                },
                z_index=node_index,
            )
        )
    return page


def _document(page_count: int, *, nodes_per_page: int = 20) -> GraphicsDocument:
    pages = [_page(index, nodes_per_page=nodes_per_page) for index in range(page_count)]
    return GraphicsDocument(
        name=f"QA baseline {page_count} páginas",
        pages=pages,
        active_page_id=pages[0].id,
        metadata={"qa_baseline": True, "pages": page_count, "nodes_per_page": nodes_per_page},
    )


def _measure(call: Callable[[], T], *, repeats: int = 1) -> tuple[T, dict[str, float | int | None]]:
    durations: list[float] = []
    cpu_durations: list[float] = []
    before = _rss_mb()
    result: T | None = None
    for _ in range(repeats):
        wall_started = time.perf_counter()
        cpu_started = time.process_time()
        result = call()
        cpu_durations.append(time.process_time() - cpu_started)
        durations.append(time.perf_counter() - wall_started)
    gc.collect()
    after = _rss_mb()
    assert result is not None
    wall_total = sum(durations)
    cpu_total = sum(cpu_durations)
    return result, {
        "repeats": repeats,
        "min_s": min(durations),
        "median_s": statistics.median(durations),
        "max_s": max(durations),
        "total_s": wall_total,
        "cpu_min_s": min(cpu_durations),
        "cpu_median_s": statistics.median(cpu_durations),
        "cpu_max_s": max(cpu_durations),
        "cpu_total_s": cpu_total,
        "cpu_to_wall_ratio": None if wall_total <= 0 else cpu_total / wall_total,
        "rss_before_mb": before,
        "rss_after_mb": after,
        "rss_delta_mb": None if before is None or after is None else after - before,
    }


def _qgui_application():
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def collect_baseline(*, output: Path, page_sizes: list[int], nodes_per_page: int) -> dict:
    startup_wall = time.perf_counter()
    startup_cpu = time.process_time()
    _app = _qgui_application()
    startup_wall_s = time.perf_counter() - startup_wall
    startup_cpu_s = time.process_time() - startup_cpu
    report: dict = {
        "schema": "srstudio/g2-qa-baseline/2",
        "python": os.sys.version,
        "platform": os.sys.platform,
        "qt_qpa_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "nodes_per_page": nodes_per_page,
        "qt_application_startup": {
            "wall_s": startup_wall_s,
            "cpu_s": startup_cpu_s,
            "rss_mb": _rss_mb(),
        },
        "cases": {},
    }

    with tempfile.TemporaryDirectory(prefix="srstudio-g2-qa-") as temp_raw:
        temp = Path(temp_raw)
        for page_count in page_sizes:
            case: dict = {}
            document, case["build"] = _measure(lambda: _document(page_count, nodes_per_page=nodes_per_page))
            assert_document_integrity(document)

            project_path = temp / f"baseline-{page_count}.srscene"
            _, case["save"] = _measure(
                lambda: save_package(document, project_path, embed_local_assets=True),
                repeats=3,
            )
            reopened, case["load"] = _measure(
                lambda: load_package(project_path, extract_assets_to=temp / f"assets-{page_count}"),
                repeats=3,
            )
            assert_document_integrity(reopened)
            case["project_bytes"] = project_path.stat().st_size
            case["nodes"] = sum(len(page.nodes) for page in reopened.pages)

            png_path = temp / f"baseline-{page_count}.png"
            png_report, case["render_png"] = _measure(
                lambda: render_png(reopened, png_path, page_index=0, dpi=96, target_width=1080),
                repeats=3,
            )
            case["png_bytes"] = png_report.output.stat().st_size
            case["png_warnings"] = len(png_report.warnings)

            pdf_path = temp / f"baseline-{page_count}.pdf"
            pdf_report, case["render_pdf"] = _measure(
                lambda: render_pdf(reopened, pdf_path, dpi=96),
                repeats=2,
            )
            case["pdf_bytes"] = pdf_report.output.stat().st_size
            case["pdf_pages"] = pdf_report.pages
            case["pdf_warnings"] = len(pdf_report.warnings)
            report["cases"][str(page_count)] = case

        longrun_document = _document(10, nodes_per_page=nodes_per_page)
        rss_samples: list[float | None] = [_rss_mb()]
        iteration_times: list[float] = []
        iteration_cpu_times: list[float] = []
        for index in range(30):
            project = temp / f"longrun-{index:02d}.srscene"
            wall_started = time.perf_counter()
            cpu_started = time.process_time()
            save_package(longrun_document, project, embed_local_assets=True)
            longrun_document = load_package(project, extract_assets_to=temp / f"longrun-assets-{index:02d}")
            assert_document_integrity(longrun_document)
            iteration_cpu_times.append(time.process_time() - cpu_started)
            iteration_times.append(time.perf_counter() - wall_started)
            if index in {4, 9, 19, 29}:
                gc.collect()
                rss_samples.append(_rss_mb())
        numeric_rss = [sample for sample in rss_samples if sample is not None]
        report["longrun_save_load_30"] = {
            "median_iteration_s": statistics.median(iteration_times),
            "max_iteration_s": max(iteration_times),
            "median_iteration_cpu_s": statistics.median(iteration_cpu_times),
            "max_iteration_cpu_s": max(iteration_cpu_times),
            "rss_samples_mb": rss_samples,
            "rss_growth_mb": None if len(numeric_rss) < 2 else numeric_rss[-1] - numeric_rss[0],
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta baseline de performance e estabilidade do SR Graphics Engine 2.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/g2-qa-baseline.json"))
    parser.add_argument("--pages", default="1,10,25", help="Casos de quantidade de páginas separados por vírgula.")
    parser.add_argument("--nodes-per-page", type=int, default=20)
    args = parser.parse_args()
    page_sizes = [int(value) for value in args.pages.split(",") if value.strip()]
    report = collect_baseline(output=args.output, page_sizes=page_sizes, nodes_per_page=args.nodes_per_page)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
