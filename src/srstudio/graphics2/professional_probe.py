from __future__ import annotations

"""Probe headless do fluxo profissional do Studio de Encartes.

Objetivo: transformar "parece utilizável" em uma verificação reproduzível.
O probe abre/importa a fonte, mede o Professional Usable Gate, persiste e
reabre `.srscene`, exporta PNG/PDF e verifica invariantes básicas do round-trip.

Não altera Golden Masters nem declara Production Ready.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
import json

from .model import GraphicsDocument
from .package import load_package, save_package
from .qt_host import load_launch_context
from .qt_renderer import render_pdf, render_png
from .usability_gate import inspect_encarte_usability


@dataclass(slots=True)
class ProfessionalProbeReport:
    source: str
    ready: bool
    usability: dict[str, Any]
    persistence_ok: bool
    png_ok: bool
    pdf_ok: bool
    page_count_before: int
    page_count_after: int
    node_count_before: int
    node_count_after: int
    slot_count_before: int
    slot_count_after: int
    output_dir: str = ""
    scene_path: str = ""
    png_path: str = ""
    pdf_path: str = ""
    gate_blockers: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_professional_probe(
    source: str | Path,
    *,
    output_dir: str | Path | None = None,
    require_semantic_products: bool = True,
    require_bound_product: bool = False,
    png_dpi: int = 96,
    pdf_dpi: int = 144,
) -> ProfessionalProbeReport:
    source_path = Path(source).expanduser().resolve()
    context = load_launch_context(source_path)
    document = context.document
    usability = inspect_encarte_usability(
        document,
        require_semantic_products=require_semantic_products,
        require_bound_product=require_bound_product,
    )
    gate_blockers = [
        f"{item.code}: {item.message}"
        for item in usability.checks
        if not item.passed and item.severity == "blocker"
    ]

    before = _counts(document)
    errors: list[str] = []
    persistence_ok = False
    png_ok = False
    pdf_ok = False
    after = dict(before)

    if output_dir is None:
        temp = TemporaryDirectory(prefix="sr-g2-professional-probe-")
        root = Path(temp.name)
    else:
        temp = None
        root = Path(output_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

    scene_path = root / f"{_safe_stem(source_path.stem)}.probe.srscene"
    png_path = root / f"{_safe_stem(source_path.stem)}.probe.png"
    pdf_path = root / f"{_safe_stem(source_path.stem)}.probe.pdf"

    try:
        try:
            saved = save_package(document, scene_path, embed_local_assets=True)
            restored = load_package(saved, extract_assets_to=root / "assets")
            after = _counts(restored)
            persistence_ok = before == after and restored.id == document.id
            if not persistence_ok:
                errors.append(f"Round-trip estrutural divergiu: before={before}, after={after}.")
        except Exception as exc:
            restored = None
            errors.append(f"Persistência: {type(exc).__name__}: {exc}")

        render_document = restored if restored is not None else document
        try:
            page_index = _active_page_index(render_document)
            png_report = render_png(render_document, png_path, page_index=page_index, dpi=max(72, int(png_dpi)))
            png_ok = png_report.ok
            if not png_ok:
                errors.append("PNG não foi materializado corretamente.")
        except Exception as exc:
            errors.append(f"PNG: {type(exc).__name__}: {exc}")

        try:
            pdf_report = render_pdf(render_document, pdf_path, dpi=max(72, int(pdf_dpi)))
            pdf_ok = pdf_report.ok and pdf_report.pages == len(render_document.pages)
            if not pdf_ok:
                errors.append("PDF não contém todas as páginas esperadas.")
        except Exception as exc:
            errors.append(f"PDF: {type(exc).__name__}: {exc}")

        ready = bool(usability.ready and persistence_ok and png_ok and pdf_ok and not errors)
        return ProfessionalProbeReport(
            source=str(source_path),
            ready=ready,
            usability=usability.to_dict(),
            persistence_ok=persistence_ok,
            png_ok=png_ok,
            pdf_ok=pdf_ok,
            page_count_before=before["pages"],
            page_count_after=after["pages"],
            node_count_before=before["nodes"],
            node_count_after=after["nodes"],
            slot_count_before=before["slots"],
            slot_count_after=after["slots"],
            output_dir=str(root) if output_dir is not None else "",
            scene_path=str(scene_path) if output_dir is not None else "",
            png_path=str(png_path) if output_dir is not None else "",
            pdf_path=str(pdf_path) if output_dir is not None else "",
            gate_blockers=gate_blockers,
            errors=errors,
        )
    finally:
        if temp is not None:
            temp.cleanup()


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="python -m srstudio.graphics2.professional_probe",
        description="Valida o fluxo headless Professional Usable do Studio de Encartes/G2.",
    )
    parser.add_argument("source", type=Path, help="PPTX/XLSX suportado ou arquivo .srscene/.zip.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Mantém os artefatos do probe nesta pasta.")
    parser.add_argument("--require-bound-product", action="store_true", help="Exige pelo menos um produto já vinculado.")
    parser.add_argument("--allow-graphics-only", action="store_true", help="Não exige ProductCard/PriceBlock/SmartSlot.")
    parser.add_argument("--json", action="store_true", help="Imprime somente JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_professional_probe(
        args.source,
        output_dir=args.output_dir,
        require_semantic_products=not bool(args.allow_graphics_only),
        require_bound_product=bool(args.require_bound_product),
    )
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if args.json:
        print(payload)
    else:
        status = "PASS" if report.ready else "NO-GO"
        print(f"G2 PROFESSIONAL PROBE: {status}")
        print(payload)
    return 0 if report.ready else 2


def _counts(document: GraphicsDocument) -> dict[str, int]:
    return {
        "pages": len(document.pages),
        "nodes": sum(len(page.nodes) for page in document.pages),
        "slots": sum(len(page.slots) for page in document.pages),
    }


def _active_page_index(document: GraphicsDocument) -> int:
    for index, page in enumerate(document.pages):
        if page.id == document.active_page_id:
            return index
    return 0


def _safe_stem(value: str) -> str:
    text = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value or "encarte"))
    return text.strip("-") or "encarte"


if __name__ == "__main__":
    raise SystemExit(main())
