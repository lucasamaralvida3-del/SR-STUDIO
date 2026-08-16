from __future__ import annotations

"""Golden Master multipágina: Canva/PPTX -> Engine 2 -> PDF oficial."""

from argparse import ArgumentParser, Namespace
from hashlib import sha256
from pathlib import Path
from statistics import fmean
from typing import Any
import json
import sys

from .fidelity import FidelityPolicy, compare_images


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-pptx-golden-master",
        description="Valida um PPTX/Canva completo contra o PDF oficial exportado do design.",
    )
    parser.add_argument("pptx", type=Path)
    parser.add_argument("reference_pdf", type=Path)
    parser.add_argument("--out", type=Path, default=Path("build/golden-master"))
    parser.add_argument("--name", default="canva-pptx")
    parser.add_argument("--target-width", type=int, default=2160)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--save-scene", action="store_true")
    defaults = FidelityPolicy()
    parser.add_argument("--min-score", type=float, default=defaults.min_score)
    parser.add_argument("--min-pixel-pass", type=float, default=defaults.min_pixel_pass_ratio)
    parser.add_argument("--pixel-tolerance", type=int, default=defaults.pixel_tolerance)
    parser.add_argument("--max-changed-ratio", type=float, default=defaults.max_changed_ratio)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_golden_master(args)
    except Exception as exc:
        print(f"SR Golden Master: ERRO: {exc}", file=sys.stderr)
        return 2


def run_golden_master(args: Namespace) -> int:
    from .import_bridge import GraphicsImportService
    from .package import save_package
    from .pdf_baseline import render_pdf_baselines
    from .quality import inspect_production_gate, store_visual_fidelity
    from .qt_renderer import qt_renderer_available, render_png

    if not qt_renderer_available():
        raise RuntimeError("PySide6 não está instalado. Instale o extra graphics2.")
    source = _require_file(args.pptx, ".pptx", "PPTX")
    reference_pdf = _require_file(args.reference_pdf, ".pdf", "PDF de referência")
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    name = _slug(args.name or source.stem)

    baselines = render_pdf_baselines(
        reference_pdf,
        output / "baseline",
        target_width=max(1, int(args.target_width)),
        dpi=max(72, int(args.dpi)),
        prefix=name,
    )
    imported = GraphicsImportService().import_file(source, project_name=source.stem)
    engine_pages = len(imported.document.pages)
    reference_pages = len(baselines)
    count_matches = engine_pages == reference_pages
    compare_count = min(engine_pages, reference_pages)
    policy = FidelityPolicy(
        min_score=float(args.min_score),
        min_pixel_pass_ratio=float(args.min_pixel_pass),
        pixel_tolerance=int(args.pixel_tolerance),
        max_changed_ratio=float(args.max_changed_ratio),
        require_same_size=True,
    ).normalized()

    page_results = []
    render_reports = []
    for index in range(compare_count):
        baseline = baselines[index]
        candidate = output / "candidate" / f"{name}-page-{index + 1:03d}.png"
        render_report = render_png(
            imported.document,
            candidate,
            page_index=index,
            dpi=max(72, int(args.dpi)),
            target_width=baseline.width,
        )
        result = compare_images(
            baseline.output,
            candidate,
            name=f"{args.name} · página {index + 1}",
            policy=policy,
            diff_path=output / "diff" / f"{name}-page-{index + 1:03d}-diff.png",
        )
        page_results.append(result)
        render_reports.append(render_report)

    aggregate = _aggregate_fidelity(page_results, count_matches, engine_pages, reference_pages)
    store_visual_fidelity(imported.document, aggregate)
    gate = inspect_production_gate(imported.document, require_visual_fidelity=True)

    scene_path = ""
    if args.save_scene:
        scene_path = str(save_package(imported.document, output / f"{name}.srscene"))

    report_path = output / f"{name}-golden-master.json"
    payload = {
        "name": args.name,
        "source": _identity(source),
        "reference_pdf": _identity(reference_pdf),
        "page_count": {
            "engine": engine_pages,
            "reference": reference_pages,
            "matches": count_matches,
        },
        "policy": {
            "min_score": policy.min_score,
            "min_pixel_pass_ratio": policy.min_pixel_pass_ratio,
            "pixel_tolerance": policy.pixel_tolerance,
            "max_changed_ratio": policy.max_changed_ratio,
            "require_same_size": policy.require_same_size,
        },
        "aggregate": aggregate,
        "pages": [result.to_dict() for result in page_results],
        "render": [
            {
                "output": str(report.output),
                "width": report.width,
                "height": report.height,
                "warnings": [
                    {
                        "code": warning.code,
                        "message": warning.message,
                        "page_id": warning.page_id,
                        "node_id": warning.node_id,
                    }
                    for warning in report.warnings
                ],
            }
            for report in render_reports
        ],
        "import_audit": imported.audit.to_dict(),
        "pptx_fidelity": dict(imported.document.metadata.get("pptx_fidelity") or {}),
        "production_gate": gate.to_dict(),
        "scene": scene_path,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"SR Golden Master: {'PASS' if gate.ready else 'FAIL'} | "
        f"{engine_pages} pág. Engine / {reference_pages} pág. referência | "
        f"mín. {aggregate['metrics']['score'] * 100:.4f}% | "
        f"média {aggregate['average_score'] * 100:.4f}% | gate {gate.score}/100"
    )
    for index, result in enumerate(page_results, start=1):
        print(
            f"  {'PASS' if result.passed else 'FAIL'} página {index}: "
            f"{result.metrics.percent:.4f}% | pixels {result.metrics.pixel_pass_ratio * 100:.4f}%"
        )
    if not count_matches:
        print(f"  FAIL PAGE_COUNT_MISMATCH: Engine={engine_pages}, referência={reference_pages}")
    for issue in gate.issues:
        if issue.severity == "blocker":
            print(f"  BLOCK {issue.code}: {issue.message}")
    print(f"  Relatório: {report_path}")
    return 0 if gate.ready and count_matches else 1


def _aggregate_fidelity(results: list[Any], count_matches: bool, engine_pages: int, reference_pages: int) -> dict[str, Any]:
    scores = [float(result.metrics.score) for result in results]
    pixel_pass = [float(result.metrics.pixel_pass_ratio) for result in results]
    changed = [float(result.metrics.changed_ratio) for result in results]
    passed = bool(results) and count_matches and all(bool(result.passed) for result in results)
    minimum_score = min(scores) if scores else 0.0
    average_score = fmean(scores) if scores else 0.0
    return {
        "passed": passed,
        "metrics": {
            # O gate usa o pior caso, não a média: uma página ruim deve barrar o release.
            "score": minimum_score,
            "pixel_pass_ratio": min(pixel_pass) if pixel_pass else 0.0,
            "changed_ratio": max(changed) if changed else 1.0,
        },
        "average_score": average_score,
        "minimum_score": minimum_score,
        "page_count_matches": count_matches,
        "engine_pages": engine_pages,
        "reference_pages": reference_pages,
        "pages": [result.to_dict() for result in results],
    }


def _identity(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"name": path.name, "size": len(raw), "sha256": sha256(raw).hexdigest()}


def _require_file(path: Path, suffix: str, label: str) -> Path:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"{label} não encontrado: {source}")
    if source.suffix.lower() != suffix:
        raise ValueError(f"{label} deve ser {suffix}: {source}")
    return source


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(value).strip())
    return cleaned.strip("-") or "golden-master"


if __name__ == "__main__":
    raise SystemExit(main())
