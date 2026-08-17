from __future__ import annotations

"""Golden Master parcial/dirigido por imagens exportadas do Canva.

Esse fluxo cobre o caso comum em que o usuário possui apenas algumas páginas
exportadas em JPG/PNG, mas o PPTX contém dezenas de slides históricos. O
manifesto associa explicitamente cada referência ao índice do slide e guarda
SHA-256/tamanho para impedir comparação acidental contra uma arte diferente.
"""

from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from statistics import fmean
from typing import Any
import json
import sys

from PIL import Image

from .fidelity import FidelityPolicy, compare_images
from .fidelity_attribution import attribute_fidelity_regions
from .fidelity_diagnostics import store_fidelity_triage
from .fidelity_triage import analyze_fidelity_regions, write_triage_report


@dataclass(slots=True, frozen=True)
class ReferenceCase:
    name: str
    page: int
    file: str
    sha256: str = ""
    width: int = 0
    height: int = 0


@dataclass(slots=True, frozen=True)
class ReferenceManifest:
    name: str
    source_name: str
    source_sha256: str
    cases: tuple[ReferenceCase, ...]


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-pptx-reference-suite",
        description="Valida páginas escolhidas de um PPTX contra JPG/PNG oficiais do Canva.",
    )
    parser.add_argument("pptx", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--references",
        type=Path,
        default=None,
        help="Diretório das imagens. Por padrão usa a pasta do manifesto.",
    )
    parser.add_argument("--out", type=Path, default=Path("build/reference-suite"))
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--save-scene", action="store_true")
    parser.add_argument("--ignore-source-hash", action="store_true")
    defaults = FidelityPolicy()
    parser.add_argument("--min-score", type=float, default=defaults.min_score)
    parser.add_argument("--min-pixel-pass", type=float, default=defaults.min_pixel_pass_ratio)
    parser.add_argument("--pixel-tolerance", type=int, default=defaults.pixel_tolerance)
    parser.add_argument("--max-changed-ratio", type=float, default=defaults.max_changed_ratio)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run_reference_suite(args)
    except Exception as exc:
        print(f"SR Reference Suite: ERRO: {exc}", file=sys.stderr)
        return 2


def load_reference_manifest(path: str | Path) -> ReferenceManifest:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Manifesto precisa conter ao menos um item em 'cases'.")
    cases: list[ReferenceCase] = []
    seen_pages: set[int] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise ValueError(f"cases[{index}] deve ser um objeto.")
        page = int(raw.get("page", -1))
        if page < 0:
            raise ValueError(f"cases[{index}].page deve ser índice zero-based >= 0.")
        if page in seen_pages:
            raise ValueError(f"Slide duplicado no manifesto: {page + 1}.")
        seen_pages.add(page)
        filename = str(raw.get("file") or "").strip()
        if not filename:
            raise ValueError(f"cases[{index}].file está vazio.")
        cases.append(
            ReferenceCase(
                name=str(raw.get("name") or f"slide-{page + 1}"),
                page=page,
                file=filename,
                sha256=str(raw.get("sha256") or "").lower(),
                width=int(raw.get("width") or 0),
                height=int(raw.get("height") or 0),
            )
        )
    return ReferenceManifest(
        name=str(data.get("name") or source.stem),
        source_name=str((data.get("source") or {}).get("name") or ""),
        source_sha256=str((data.get("source") or {}).get("sha256") or "").lower(),
        cases=tuple(cases),
    )


def verify_reference_case(case: ReferenceCase, root: str | Path) -> Path:
    path = (Path(root) / case.file).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Referência não encontrada: {path}")
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    if case.sha256 and digest != case.sha256:
        raise ValueError(f"SHA-256 divergente em {case.file}: esperado {case.sha256}, obtido {digest}")
    with Image.open(path) as image:
        width, height = image.size
    if case.width and width != case.width:
        raise ValueError(f"Largura divergente em {case.file}: esperado {case.width}, obtido {width}")
    if case.height and height != case.height:
        raise ValueError(f"Altura divergente em {case.file}: esperado {case.height}, obtido {height}")
    return path


def run_reference_suite(args: Namespace) -> int:
    from .import_bridge import GraphicsImportService
    from .package import save_package
    from .quality import inspect_production_gate, store_visual_fidelity
    from .qt_renderer import qt_renderer_available, render_png
    from .scene_fingerprint import store_scene_fingerprint

    if not qt_renderer_available():
        raise RuntimeError("PySide6 não está instalado. Instale o extra graphics2.")
    pptx = Path(args.pptx).resolve()
    if not pptx.is_file() or pptx.suffix.lower() != ".pptx":
        raise FileNotFoundError(f"PPTX não encontrado: {pptx}")
    manifest_path = Path(args.manifest).resolve()
    manifest = load_reference_manifest(manifest_path)
    source_identity = _identity(pptx)
    if manifest.source_sha256 and not bool(args.ignore_source_hash):
        if source_identity["sha256"] != manifest.source_sha256:
            raise ValueError(
                "PPTX não corresponde ao Golden Master: "
                f"esperado {manifest.source_sha256}, obtido {source_identity['sha256']}"
            )

    reference_root = Path(args.references).resolve() if args.references else manifest_path.parent
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    imported = GraphicsImportService().import_file(pptx, project_name=pptx.stem)
    fingerprint = store_scene_fingerprint(imported.document)
    policy = FidelityPolicy(
        min_score=float(args.min_score),
        min_pixel_pass_ratio=float(args.min_pixel_pass),
        pixel_tolerance=int(args.pixel_tolerance),
        max_changed_ratio=float(args.max_changed_ratio),
        require_same_size=True,
    ).normalized()

    results = []
    render_reports = []
    case_payloads = []
    portable_triage_by_case: list[dict[str, Any]] = []
    for case in manifest.cases:
        if case.page >= len(imported.document.pages):
            raise IndexError(f"Manifesto pede slide {case.page + 1}, mas o Engine importou {len(imported.document.pages)} páginas.")
        baseline = verify_reference_case(case, reference_root)
        with Image.open(baseline) as image:
            target_width = int(image.width)
        slug = _slug(case.name)
        candidate = output / "candidate" / f"slide-{case.page + 1:03d}-{slug}.png"
        report = render_png(
            imported.document,
            candidate,
            page_index=case.page,
            dpi=max(72, int(args.dpi)),
            target_width=target_width,
        )
        result = compare_images(
            baseline,
            candidate,
            name=case.name,
            policy=policy,
            diff_path=output / "diff" / f"slide-{case.page + 1:03d}-{slug}-diff.png",
        )
        triage = analyze_fidelity_regions(
            baseline,
            candidate,
            pixel_tolerance=policy.pixel_tolerance,
            heatmap_path=output / "triage" / f"slide-{case.page + 1:03d}-{slug}-heatmap.png",
        )
        triage_path = write_triage_report(
            triage,
            output / "triage" / f"slide-{case.page + 1:03d}-{slug}-triage.json",
        )
        attribution = attribute_fidelity_regions(triage, imported.document.pages[case.page])
        attribution_path = output / "triage" / f"slide-{case.page + 1:03d}-{slug}-attribution.json"
        attribution_path.parent.mkdir(parents=True, exist_ok=True)
        attribution_path.write_text(
            json.dumps(attribution.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        portable_triage = {
            "available": True,
            "spatial": triage.to_dict(),
            "attribution": attribution.to_dict(),
        }
        results.append(result)
        render_reports.append(report)
        portable_triage_by_case.append(portable_triage)
        case_payloads.append(
            {
                "name": case.name,
                "page": case.page,
                "slide": case.page + 1,
                "reference": _identity(baseline),
                "result": result.to_dict(),
                "triage": triage.to_dict(),
                "triage_report": str(triage_path),
                "attribution": attribution.to_dict(),
                "attribution_report": str(attribution_path),
            }
        )

    aggregate = _aggregate(results)
    store_visual_fidelity(imported.document, aggregate)
    if results:
        worst_index = min(range(len(results)), key=lambda index: float(results[index].metrics.score))
        store_fidelity_triage(imported.document, portable_triage_by_case[worst_index])
        imported.document.metadata["visual_fidelity_worst_case"] = {
            "name": manifest.cases[worst_index].name,
            "page": manifest.cases[worst_index].page,
            "slide": manifest.cases[worst_index].page + 1,
            "score": float(results[worst_index].metrics.score),
        }
    gate = inspect_production_gate(imported.document, require_visual_fidelity=True)
    scene_path = ""
    if args.save_scene:
        scene_path = str(save_package(imported.document, output / f"{_slug(manifest.name)}.srscene"))
    pptx_structure = dict(imported.document.metadata.get("pptx_structure") or {})
    pptx_mapping = dict(imported.document.metadata.get("pptx_mapping_audit") or {})
    payload = {
        "name": manifest.name,
        "source": source_identity,
        "manifest": str(manifest_path),
        "scene_fingerprint": fingerprint.to_dict(),
        "aggregate": aggregate,
        "worst_case": dict(imported.document.metadata.get("visual_fidelity_worst_case") or {}),
        "cases": case_payloads,
        "render": [
            {
                "output": str(item.output),
                "width": item.width,
                "height": item.height,
                "warnings": [
                    {"code": w.code, "message": w.message, "page_id": w.page_id, "node_id": w.node_id}
                    for w in item.warnings
                ],
            }
            for item in render_reports
        ],
        "import_audit": imported.audit.to_dict(),
        "pptx_structure": pptx_structure,
        "pptx_mapping": pptx_mapping,
        "pptx_effects": dict(imported.document.metadata.get("pptx_effects") or {}),
        "pptx_effect_mapping": dict(imported.document.metadata.get("pptx_effect_mapping") or {}),
        "pptx_fidelity": dict(imported.document.metadata.get("pptx_fidelity") or {}),
        "production_gate": gate.to_dict(),
        "scene": scene_path,
    }
    report_path = output / f"{_slug(manifest.name)}-reference-suite.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"SR Reference Suite: {'PASS' if gate.ready and aggregate['passed'] else 'FAIL'} | "
        f"{len(results)} referência(s) | mínimo {aggregate['minimum_score'] * 100:.4f}% | "
        f"média {aggregate['average_score'] * 100:.4f}% | gate {gate.score}/100"
    )
    if pptx_mapping:
        print(
            "  Mapeamento OOXML: "
            f"texto={float(pptx_mapping.get('text_coverage', 1.0)) * 100:.2f}% · "
            f"imagem={float(pptx_mapping.get('image_coverage', 1.0)) * 100:.2f}% · "
            f"fillRect={float(pptx_mapping.get('fill_rect_coverage', 1.0)) * 100:.2f}% · "
            f"outset={float(pptx_mapping.get('fill_outset_coverage', 1.0)) * 100:.2f}% · "
            f"máscaras={float(pptx_mapping.get('image_clip_coverage', 1.0)) * 100:.2f}%"
        )
    for case, result, case_payload in zip(manifest.cases, results, case_payloads):
        triage = case_payload["triage"]
        regions = list(triage.get("regions") or [])
        region_note = ""
        if regions:
            first = regions[0]
            region_note = (
                f" · maior região x={first['x']} y={first['y']} "
                f"{first['width']}×{first['height']}"
            )
        suspect_note = _top_suspect_note(case_payload.get("attribution") or {})
        print(
            f"  {'PASS' if result.passed else 'FAIL'} slide {case.page + 1}: "
            f"{case.name} · {result.metrics.percent:.4f}%{region_note}{suspect_note}"
        )
    print(f"  Relatório: {report_path}")
    return 0 if gate.ready and aggregate["passed"] else 1


def _top_suspect_note(attribution: dict[str, Any]) -> str:
    regions = list(attribution.get("regions") or [])
    if not regions:
        return ""
    suspects = list((regions[0] or {}).get("suspects") or [])
    if not suspects:
        return " · sem node SR Scene associado"
    suspect = suspects[0]
    role = str(suspect.get("binding_role") or suspect.get("kind") or "node")
    name = str(suspect.get("name") or suspect.get("node_id") or "sem nome")
    return f" · provável {role}: {name}"


def _aggregate(results: list[Any]) -> dict[str, Any]:
    scores = [float(result.metrics.score) for result in results]
    pixel_pass = [float(result.metrics.pixel_pass_ratio) for result in results]
    changed = [float(result.metrics.changed_ratio) for result in results]
    return {
        "passed": bool(results) and all(bool(result.passed) for result in results),
        "metrics": {
            "score": min(scores) if scores else 0.0,
            "pixel_pass_ratio": min(pixel_pass) if pixel_pass else 0.0,
            "changed_ratio": max(changed) if changed else 1.0,
        },
        "minimum_score": min(scores) if scores else 0.0,
        "average_score": fmean(scores) if scores else 0.0,
        "cases": [result.to_dict() for result in results],
    }


def _identity(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"name": path.name, "size": len(raw), "sha256": sha256(raw).hexdigest()}


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(value).strip())
    return cleaned.strip("-") or "reference"


if __name__ == "__main__":
    raise SystemExit(main())
