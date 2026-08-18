from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import statistics
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from srstudio.graphics2.export_output import export_pdf, export_png, export_raster_batch
from srstudio.graphics2.model import CoordinateUnit, GraphicsDocument, GraphicsPage


def _document(page_count: int = 10) -> GraphicsDocument:
    document = GraphicsDocument(name="G2 export benchmark")
    document.pages = [
        GraphicsPage(
            name=f"Página {index + 1}",
            width=1080,
            height=1350,
            unit=CoordinateUnit.PIXEL,
            background="#FFFFFF",
        )
        for index in range(page_count)
    ]
    document.active_page_id = document.pages[0].id
    return document


def _rss_bytes() -> int:
    if os.name == "nt":
        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if ok:
            return int(counters.WorkingSetSize)
        return 0

    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except Exception:
        return 0


def _measure(callable_):
    baseline = _rss_bytes()
    peak = baseline
    stop = threading.Event()

    def sampler() -> None:
        nonlocal peak
        while not stop.wait(0.01):
            peak = max(peak, _rss_bytes())

    thread = threading.Thread(target=sampler, name="g2-export-rss-sampler", daemon=True)
    thread.start()
    started = time.perf_counter()
    try:
        result = callable_()
    finally:
        elapsed = time.perf_counter() - started
        stop.set()
        thread.join(timeout=1.0)
        peak = max(peak, _rss_bytes())
    return result, elapsed, max(0, peak - baseline)


def run_benchmark(output: Path) -> dict[str, float | int | str]:
    document = _document(10)
    with tempfile.TemporaryDirectory(prefix="sr-g2-export-bench-") as raw_dir:
        root = Path(raw_dir)

        first, first_seconds, first_rss = _measure(
            lambda: export_png(document, root / "first.png", page_index=0, target_width=1080, dpi=300)
        )

        repeat_times: list[float] = []
        repeat_peaks: list[int] = []
        for index in range(3):
            _, elapsed, rss_delta = _measure(
                lambda index=index: export_png(
                    document,
                    root / f"repeat-{index}.png",
                    page_index=0,
                    target_width=1080,
                    dpi=300,
                )
            )
            repeat_times.append(elapsed)
            repeat_peaks.append(rss_delta)

        batch, batch_seconds, batch_rss = _measure(
            lambda: export_raster_batch(
                document,
                root / "batch",
                raster_format="png",
                target_width=1080,
                dpi=300,
            )
        )

        pdf, pdf_seconds, pdf_rss = _measure(
            lambda: export_pdf(document, root / "ten-pages.pdf", dpi=300)
        )

        a4 = GraphicsDocument(name="A4 benchmark")
        a4.pages = [
            GraphicsPage(
                name="A4",
                width=210,
                height=297,
                unit=CoordinateUnit.MILLIMETER,
                background="#FFFFFF",
            )
        ]
        a4.active_page_id = a4.pages[0].id
        a4_png, a4_seconds, a4_rss = _measure(lambda: export_png(a4, root / "a4-300.png", dpi=300))

        result: dict[str, float | int | str] = {
            "first_png_ms": round(first_seconds * 1000.0, 2),
            "first_png_peak_rss_delta_mb": round(first_rss / (1024 * 1024), 2),
            "repeat_png_mean_ms": round(statistics.mean(repeat_times) * 1000.0, 2),
            "repeat_png_min_ms": round(min(repeat_times) * 1000.0, 2),
            "repeat_png_peak_rss_delta_mb": round(max(repeat_peaks, default=0) / (1024 * 1024), 2),
            "png_batch_pages": batch.pages,
            "png_batch_total_ms": round(batch_seconds * 1000.0, 2),
            "png_batch_per_page_ms": round(batch_seconds * 1000.0 / max(1, batch.pages), 2),
            "png_batch_peak_rss_delta_mb": round(batch_rss / (1024 * 1024), 2),
            "pdf_pages": pdf.pages,
            "pdf_total_ms": round(pdf_seconds * 1000.0, 2),
            "pdf_per_page_ms": round(pdf_seconds * 1000.0 / max(1, pdf.pages), 2),
            "pdf_peak_rss_delta_mb": round(pdf_rss / (1024 * 1024), 2),
            "a4_300_width": a4_png.width,
            "a4_300_height": a4_png.height,
            "a4_300_ms": round(a4_seconds * 1000.0, 2),
            "a4_300_peak_rss_delta_mb": round(a4_rss / (1024 * 1024), 2),
            "platform": os.name,
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="G2 export output performance probe")
    parser.add_argument("--output", type=Path, default=Path("g2-export-benchmark.json"))
    args = parser.parse_args()
    result = run_benchmark(args.output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
