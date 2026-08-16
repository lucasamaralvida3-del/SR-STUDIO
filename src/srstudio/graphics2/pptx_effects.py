from __future__ import annotations

"""Auditoria de efeitos DrawingML usados por PPTX/Canva reais.

A fidelidade visual não depende somente de geometria, texto e imagens. Sombras,
gradientes, transparência, brilho e efeitos 3D podem alterar uma região grande do
Golden Master mesmo quando todos os nodes foram importados corretamente. Este
módulo mede esses recursos diretamente no OOXML sem tentar adivinhar suporte do
renderer. O relatório é determinístico e pode ser usado para priorizar a próxima
implementação a partir do corpus real.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
import json
import re
import sys
import zipfile

from xml.etree import ElementTree as ET

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS = {"a": _A, "p": _P}
_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")

_EFFECT_PATHS: dict[str, str] = {
    "gradient_fills": ".//a:gradFill",
    "pattern_fills": ".//a:pattFill",
    "outer_shadows": ".//a:outerShdw",
    "inner_shadows": ".//a:innerShdw",
    "glows": ".//a:glow",
    "reflections": ".//a:reflection",
    "soft_edges": ".//a:softEdge",
    "blurs": ".//a:blur",
    "effect_dags": ".//a:effectDag",
    "scene_3d": ".//a:scene3d",
    "shape_3d": ".//a:sp3d",
}

_ALPHA_TAGS = ("alpha", "alphaMod", "alphaOff", "alphaModFix")


@dataclass(slots=True, frozen=True)
class SlideEffectStats:
    slide: int
    gradient_fills: int = 0
    pattern_fills: int = 0
    alpha_modifiers: int = 0
    outer_shadows: int = 0
    inner_shadows: int = 0
    glows: int = 0
    reflections: int = 0
    soft_edges: int = 0
    blurs: int = 0
    effect_dags: int = 0
    scene_3d: int = 0
    shape_3d: int = 0

    @property
    def advanced_effects(self) -> int:
        return (
            self.gradient_fills
            + self.pattern_fills
            + self.outer_shadows
            + self.inner_shadows
            + self.glows
            + self.reflections
            + self.soft_edges
            + self.blurs
            + self.effect_dags
            + self.scene_3d
            + self.shape_3d
        )

    def to_dict(self) -> dict[str, int]:
        payload = asdict(self)
        payload["advanced_effects"] = self.advanced_effects
        return payload


@dataclass(slots=True, frozen=True)
class PptxEffectAudit:
    source: str
    slides: tuple[SlideEffectStats, ...] = field(default_factory=tuple)

    @property
    def totals(self) -> dict[str, int]:
        keys = list(_EFFECT_PATHS) + ["alpha_modifiers"]
        totals = {key: sum(getattr(slide, key) for slide in self.slides) for key in keys}
        totals["advanced_effects"] = sum(slide.advanced_effects for slide in self.slides)
        totals["slides_with_advanced_effects"] = sum(1 for slide in self.slides if slide.advanced_effects)
        totals["slides_with_alpha"] = sum(1 for slide in self.slides if slide.alpha_modifiers)
        totals["slides"] = len(self.slides)
        return totals

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "totals": self.totals,
            "slides": [slide.to_dict() for slide in self.slides],
        }


def audit_pptx_effects(source: str | Path) -> PptxEffectAudit:
    """Conta efeitos DrawingML por slide sem alterar o arquivo fonte."""

    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pptx":
        raise ValueError("A auditoria de efeitos requer um arquivo .pptx.")

    stats: list[SlideEffectStats] = []
    with zipfile.ZipFile(path) as archive:
        slide_entries = sorted(_slide_entries(archive.namelist()), key=lambda item: item[0])
        for slide_number, entry in slide_entries:
            try:
                root = ET.fromstring(archive.read(entry))
            except ET.ParseError as exc:
                raise ValueError(f"OOXML inválido em {entry}: {exc}") from exc
            counts = {key: len(root.findall(xpath, _NS)) for key, xpath in _EFFECT_PATHS.items()}
            counts["alpha_modifiers"] = _count_alpha(root)
            stats.append(SlideEffectStats(slide=slide_number, **counts))
    return PptxEffectAudit(source=str(path), slides=tuple(stats))


def _slide_entries(names: Iterable[str]) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for name in names:
        match = _SLIDE_RE.match(name)
        if match:
            result.append((int(match.group(1)), name))
    return result


def _count_alpha(root: ET.Element) -> int:
    total = 0
    for tag in _ALPHA_TAGS:
        total += len(root.findall(f".//a:{tag}", _NS))
    return total


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-pptx-effects",
        description="Audita gradientes, transparência, sombras e demais efeitos DrawingML de um PPTX.",
    )
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path, help="Grava o relatório completo em JSON.")
    parser.add_argument("--slides", action="store_true", help="Exibe também os slides que possuem efeitos avançados.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = audit_pptx_effects(args.pptx)
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    totals = report.totals
    print(
        "PPTX Effects: "
        f"slides={totals['slides']} "
        f"advanced={totals['advanced_effects']} "
        f"gradients={totals['gradient_fills']} "
        f"shadows={totals['outer_shadows'] + totals['inner_shadows']} "
        f"alpha={totals['alpha_modifiers']}"
    )
    if args.slides:
        for slide in report.slides:
            if slide.advanced_effects or slide.alpha_modifiers:
                print(
                    f"slide {slide.slide}: advanced={slide.advanced_effects} "
                    f"gradients={slide.gradient_fills} shadows={slide.outer_shadows + slide.inner_shadows} "
                    f"alpha={slide.alpha_modifiers}"
                )
    if args.json_path:
        target = args.json_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
