from __future__ import annotations

"""CLI de regressão visual para projetos reais do SR Graphics Engine 2."""

from argparse import ArgumentParser, Namespace
from hashlib import sha256
from pathlib import Path
import json
import sys

from .fidelity import FidelityPolicy, compare_images, load_manifest, run_suite, write_report
from .fidelity_attribution import attribute_fidelity_regions
from .fidelity_triage import analyze_fidelity_regions, write_triage_report


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

    pptx_audit = sub.add_parser(
        "pptx-audit",
        help="Importa um PPTX/Canva real e grava auditoria estrutural + relatório de fidelidade OOXML",
    )
    pptx_audit.add_argument("pptx", type=Path)
    pptx_audit.add_argument("--out", type=Path, default=Path("build/fidelity"))
    pptx_audit.add_argument("--name", default="pptx-audit")
    pptx_audit.add_argument("--save-scene", action="store_true")

    pptx_render = sub.add_parser(
        "pptx-render-compare",
        help="Importa PPTX/Canva -> SR Scene 2 -> Qt PNG e compara diretamente com uma referência",
    )
    pptx_render.add_argument("pptx", type=Path)
    pptx_render.add_argument("baseline", type=Path)
    pptx_render.add_argument("--page", type=int, default=0)
    pptx_render.add_argument("--dpi", type=int, default=300)
    pptx_render.add_argument(
        "--target-width",
        type=int,
        default=0,
        help="Largura do PNG candidato. Zero usa automaticamente a largura da imagem de referência.",
    )
    pptx_render.add_argument("--out", type=Path, default=Path("build/fidelity"))
    pptx_render.add_argument("--name", default="pptx")
    pptx_render.add_argument("--save-scene", action="store_true")
    _add_policy_arguments(pptx_render)
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
        if args.command == "pptx-audit":
            return _pptx_audit(args)
        if args.command == "pptx-render-compare":
            return _pptx_render_compare(args)
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
    if not 0 <= args.page < len(document.pages):
        raise IndexError(f"Página {args.page} inexistente no SR Scene carregado.")
    stem = _slug(args.name)
    candidate = output / f"{stem}-candidate.png"
    render_png(document, candidate, page_index=args.page, dpi=args.dpi)
    policy = _policy_from(args)
    result = compare_images(
        args.baseline,
        candidate,
        name=args.name,
        policy=policy,
        diff_path=output / f"{stem}-diff.png",
    )
    triage = _scene_aware_triage(
        args.baseline,
        candidate,
        document.pages[args.page],
        output=output,
        stem=stem,
        pixel_tolerance=policy.pixel_tolerance,
    )
    report = write_report(result, output / f"{stem}-report.json")
    _print_case(result, report)
    _print_triage_summary(triage)
    return 0 if result.passed else 1


def _pptx_audit(args: Namespace) -> int:
    from .import_bridge import GraphicsImportService
    from .package import save_package
    from .quality import inspect_production_gate

    source = _require_pptx(args.pptx)
    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    imported = GraphicsImportService().import_file(source, project_name=source.stem)
    gate = inspect_production_gate(imported.document, require_visual_fidelity=False)
    stem = _slug(args.name or source.stem)
    scene_path = ""
    if args.save_scene:
        scene_path = str(save_package(imported.document, output / f"{stem}.srscene"))
    payload = _pptx_diagnostic_payload(source, imported)
    payload["production_gate"] = gate.to_dict()
    payload["scene"] = scene_path
    report = output / f"{stem}-audit.json"
    _write_json(report, payload)
    print(
        f"SR Fidelity Lab: {'PASS' if gate.ready else 'FAIL'} | PPTX audit | "
        f"{imported.audit.pages} pág. | {imported.audit.nodes} nodes | "
        f"{imported.audit.slots} slots | confiança {imported.audit.confidence * 100:.2f}% | "
        f"gate {gate.score}/100 | {report}"
    )
    return 0 if gate.ready else 1


def _pptx_render_compare(args: Namespace) -> int:
    from PIL import Image

    from .import_bridge import GraphicsImportService
    from .package import save_package
    from .quality import inspect_production_gate, store_visual_fidelity
    from .qt_renderer import qt_renderer_available, render_png

    if not qt_renderer_available():
        raise RuntimeError("PySide6 não está instalado. Instale o extra graphics2.")
    source = _require_pptx(args.pptx)
    baseline = Path(args.baseline)
    if not baseline.is_file():
        raise FileNotFoundError(f"Imagem de referência não encontrada: {baseline}")

    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    stem = _slug(args.name or source.stem)
    imported = GraphicsImportService().import_file(source, project_name=source.stem)
    if not 0 <= args.page < len(imported.document.pages):
        raise IndexError(f"Página {args.page} inexistente no PPTX importado.")

    with Image.open(baseline) as reference:
        baseline_width = int(reference.width)
    target_width = int(args.target_width) if int(args.target_width or 0) > 0 else baseline_width
    candidate = output / f"{stem}-candidate.png"
    render_report = render_png(
        imported.document,
        candidate,
        page_index=args.page,
        dpi=args.dpi,
        target_width=target_width,
    )
    policy = _policy_from(args)
    fidelity = compare_images(
        baseline,
        candidate,
        name=args.name,
        policy=policy,
        diff_path=output / f"{stem}-diff.png",
    )
    triage = _scene_aware_triage(
        baseline,
        candidate,
        imported.document.pages[args.page],
        output=output,
        stem=stem,
        pixel_tolerance=policy.pixel_tolerance,
    )
    store_visual_fidelity(imported.document, fidelity)
    gate = inspect_production_gate(imported.document, require_visual_fidelity=True)

    scene_path = ""
    if args.save_scene:
        scene_path = str(save_package(imported.document, output / f"{stem}.srscene"))
    payload = {
        "source": _source_identity(source),
        "page": args.page,
        "target_width": target_width,
        "scene": scene_path,
        "import": _pptx_diagnostic_payload(source, imported),
        "production_gate": gate.to_dict(),
        "render": {
            "output": str(render_report.output),
            "width": render_report.width,
            "height": render_report.height,
            "warnings": [
                {
                    "code": warning.code,
                    "message": warning.message,
                    "page_id": warning.page_id,
                    "node_id": warning.node_id,
                }
                for warning in render_report.warnings
            ],
        },
        "fidelity": fidelity.to_dict(),
        "triage": triage,
    }
    report = output / f"{stem}-pipeline-report.json"
    _write_json(report, payload)
    _print_case(fidelity, report)
    _print_triage_summary(triage)
    print(f"  Production Gate: {'PASS' if gate.ready else 'FAIL'} · {gate.score}/100")
    for issue in gate.issues:
        if issue.severity == "blocker":
            print(f"  - {issue.code}: {issue.message}")
    return 0 if gate.ready else 1


def _scene_aware_triage(
    baseline: str | Path,
    candidate: str | Path,
    page,
    *,
    output: Path,
    stem: str,
    pixel_tolerance: int,
) -> dict:
    """Gera triagem espacial + atribuição SR Scene sem influenciar PASS/FAIL.

    O Fidelity Gate continua sendo a autoridade. Se a triagem não puder rodar —
    por exemplo, quando ``--allow-resize`` compara imagens de dimensões diferentes —
    o pipeline registra a indisponibilidade em vez de transformar diagnóstico em falha.
    """

    heatmap = output / f"{stem}-triage-heatmap.png"
    triage_report_path = output / f"{stem}-triage.json"
    attribution_report_path = output / f"{stem}-attribution.json"
    try:
        triage = analyze_fidelity_regions(
            baseline,
            candidate,
            pixel_tolerance=pixel_tolerance,
            heatmap_path=heatmap,
        )
    except ValueError as exc:
        return {
            "available": False,
            "reason": str(exc),
            "triage_report": "",
            "heatmap": "",
            "attribution_report": "",
        }

    write_triage_report(triage, triage_report_path)
    attribution = attribute_fidelity_regions(triage, page)
    _write_json(attribution_report_path, attribution.to_dict())
    return {
        "available": True,
        "triage_report": str(triage_report_path),
        "heatmap": str(heatmap),
        "attribution_report": str(attribution_report_path),
        "spatial": triage.to_dict(),
        "attribution": attribution.to_dict(),
    }


def _print_triage_summary(payload: dict) -> None:
    if not payload.get("available"):
        print(f"  Triage scene-aware: indisponível · {payload.get('reason', 'sem motivo informado')}")
        return
    attribution = dict(payload.get("attribution") or {})
    regions = list(attribution.get("regions") or [])
    if not regions:
        print("  Triage scene-aware: nenhuma divergência acima da tolerância.")
        return

    print(f"  Triage scene-aware: {len(regions)} região(ões) prioritária(s)")
    for item in regions[:3]:
        suspects = list(item.get("suspects") or [])
        region_index = int(item.get("region_index") or 0)
        if not suspects:
            print(f"    #{region_index}: sem nó SR Scene correspondente")
            continue
        suspect = suspects[0]
        semantic = str(suspect.get("binding_role") or suspect.get("kind") or "nó")
        name = str(suspect.get("name") or suspect.get("node_id") or "sem nome")
        print(
            f"    #{region_index}: {semantic} · {name} · "
            f"score suspeito {float(suspect.get('score') or 0.0):.3f}"
        )
        hint = str(suspect.get("diagnostic_hint") or "").strip()
        if hint:
            print(f"       ↳ {hint}")


def _pptx_diagnostic_payload(source: Path, imported) -> dict:
    return {
        "source": _source_identity(source),
        "summary": {
            "products_added": imported.summary.products_added,
            "cards_added": imported.summary.cards_added,
            "images_matched": imported.summary.images_matched,
            "images_learned": imported.summary.images_learned,
            "layouts_learned": imported.summary.layouts_learned,
            "warnings": list(imported.summary.warnings),
        },
        "audit": imported.audit.to_dict(),
        "pptx_fidelity": dict(imported.document.metadata.get("pptx_fidelity") or {}),
        "embedded_fonts": list(imported.document.metadata.get("embedded_fonts") or []),
    }


def _source_identity(source: Path) -> dict:
    raw = source.read_bytes()
    return {
        "name": source.name,
        "size": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }


def _require_pptx(path: Path) -> Path:
    source = Path(path)
    if source.suffix.lower() != ".pptx":
        raise ValueError(f"Arquivo deve ser .pptx: {source}")
    if not source.is_file():
        raise FileNotFoundError(f"PPTX não encontrado: {source}")
    return source


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
