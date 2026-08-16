from __future__ import annotations

"""CLI de regressão visual para projetos reais do SR Graphics Engine 2."""

from argparse import ArgumentParser, Namespace
from pathlib import Path
import json
import sys

from .fidelity import FidelityPolicy, compare_images, load_manifest, run_suite, write_report


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="sr-fidelity-lab", description="SR Visual Fidelity Lab")
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser("compare", help="Compara uma referência com uma renderização candidata")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--name", default="visual")
    compare.add_argument("--out", type=Path, default=Path("build/fidelity"))
    _add_policy_arguments(compare)

    suite = sub.add_parser("suite", help="Executa um manifesto com vários projetos de referência")
    suite.add_argument("manifest", type=Path)
    suite.add_argument("--out", type=Path, default=Path("build/fidelity"))

    render = sub.add_parser(
        "render-compare",
        help="Renderiza um .srscene com o renderer Qt e compara com a referência",
    )
    render.add_argument("scene", type=Path)
    render.add_argument("baseline", type=Path)
    render.add_argument("--page", type=int, default=0)
    render.add_argument("--dpi", type=int, default=300)
    render.add_argument("--out", type=Path, default=Path("build/fidelity"))
    render.add_argument("--name", default="srscene")
    _add_policy_arguments(render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compare":
            return _compare(args)
        if args.command == "suite":
            return _suite(args)
        if args.command == "render-compare":
            return _render_compare(args)
    except Exception as exc:
        print(f"SR Fidelity Lab: ERRO: {exc}", file=sys.stderr)
        return 2
    return 2


def _compare(args: Namespace) -> int:
    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    result = compare_images(
        args.baseline,
        args.candidate,
        name=args.name,
        policy=_policy_from(args),
        diff_path=output / f"{_slug(args.name)}-diff.png",
    )
    report = write_report(result, output / f"{_slug(args.name)}-report.json")
    _print_case(result, report)
    return 0 if result.passed else 1


def _suite(args: Namespace) -> int:
    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    result = run_suite(load_manifest(args.manifest), artifacts_dir=output)
    report = write_report(result, output / "suite-report.json")
    print(
        f"SR Fidelity Lab: {'PASS' if result.passed else 'FAIL'} | "
        f"{len(result.cases)} caso(s) | média {result.average_score * 100:.4f}% | {report}"
    )
    for case in result.cases:
        print(
            f"  {'PASS' if case.passed else 'FAIL'} {case.name}: "
            f"{case.metrics.percent:.4f}% | pixels {case.metrics.pixel_pass_ratio * 100:.4f}%"
        )
        for reason in case.reasons:
            print(f"    - {reason}")
    return 0 if result.passed else 1


def _render_compare(args: Namespace) -> int:
    # Imports tardios: o modo compare/suite continua leve e funciona sem Qt.
    from .package import load_package
    from .qt_renderer import qt_renderer_available, render_png

    if not qt_renderer_available():
        raise RuntimeError("PySide6 não está instalado. Instale o extra graphics2.")
    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    assets_dir = output / "assets"
    document = load_package(args.scene, extract_assets_to=assets_dir)
    candidate = output / f"{_slug(args.name)}-candidate.png"
    render_png(document, candidate, page_index=args.page, dpi=args.dpi)
    result = compare_images(
        args.baseline,
        candidate,
        name=args.name,
        policy=_policy_from(args),
        diff_path=output / f"{_slug(args.name)}-diff.png",
    )
    report = write_report(result, output / f"{_slug(args.name)}-report.json")
    _print_case(result, report)
    return 0 if result.passed else 1


def _add_policy_arguments(parser: ArgumentParser) -> None:
    defaults = FidelityPolicy()
    parser.add_argument("--min-score", type=float, default=defaults.min_score)
    parser.add_argument("--min-pixel-pass", type=float, default=defaults.min_pixel_pass_ratio)
    parser.add_argument("--pixel-tolerance", type=int, default=defaults.pixel_tolerance)
    parser.add_argument("--max-changed-ratio", type=float, default=defaults.max_changed_ratio)
    parser.add_argument("--allow-resize", action="store_true")


def _policy_from(args: Namespace) -> FidelityPolicy:
    return FidelityPolicy(
        min_score=args.min_score,
        min_pixel_pass_ratio=args.min_pixel_pass,
        pixel_tolerance=args.pixel_tolerance,
        max_changed_ratio=args.max_changed_ratio,
        require_same_size=not args.allow_resize,
    ).normalized()


def _print_case(result, report: Path) -> None:
    print(
        f"SR Fidelity Lab: {'PASS' if result.passed else 'FAIL'} | {result.name} | "
        f"score {result.metrics.percent:.4f}% | "
        f"pixels {result.metrics.pixel_pass_ratio * 100:.4f}% | {report}"
    )
    if result.reasons:
        print(json.dumps(result.reasons, ensure_ascii=False, indent=2))


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned.strip("-") or "visual"


if __name__ == "__main__":
    raise SystemExit(main())
