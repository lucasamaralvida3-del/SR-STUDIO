from __future__ import annotations

"""Auditoria de efeitos DrawingML usados por PPTX/Canva reais.

A fidelidade visual não depende somente de geometria, texto e imagens. Sombras,
gradientes, transparência, brilho e efeitos 3D podem alterar uma região grande do
Golden Master mesmo quando todos os nodes foram importados corretamente. Este
módulo mede esses recursos diretamente no OOXML sem tentar adivinhar suporte do
renderer. O relatório é determinístico e pode ser usado para priorizar a próxima
implementação a partir do corpus real.

Além dos totais por slide, a auditoria atribui cada efeito ao shape OOXML mais
próximo. Isso permite que o Fidelity Lab avance de "há sombras nesta página" para
"o shape 42 / Preço tem sombra", sem duplicar efeitos de filhos dentro de grupos.
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
_SHAPE_TAGS = {
    f"{{{_P}}}sp": "shape",
    f"{{{_P}}}pic": "picture",
    f"{{{_P}}}grpSp": "group",
    f"{{{_P}}}cxnSp": "connector",
    f"{{{_P}}}graphicFrame": "graphic_frame",
}
_CNVPR_PATHS = {
    "shape": "./p:nvSpPr/p:cNvPr",
    "picture": "./p:nvPicPr/p:cNvPr",
    "group": "./p:nvGrpSpPr/p:cNvPr",
    "connector": "./p:nvCxnSpPr/p:cNvPr",
    "graphic_frame": "./p:nvGraphicFramePr/p:cNvPr",
}


def _advanced_count(payload: object) -> int:
    return sum(int(getattr(payload, key, 0) or 0) for key in _EFFECT_PATHS)


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
        return _advanced_count(self)

    def to_dict(self) -> dict[str, int]:
        payload = asdict(self)
        payload["advanced_effects"] = self.advanced_effects
        return payload


@dataclass(slots=True, frozen=True)
class ShapeEffectStats:
    slide: int
    shape_id: str
    shape_name: str
    shape_kind: str
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
        return _advanced_count(self)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["advanced_effects"] = self.advanced_effects
        return payload


@dataclass(slots=True, frozen=True)
class PptxEffectAudit:
    source: str
    slides: tuple[SlideEffectStats, ...] = field(default_factory=tuple)
    shapes: tuple[ShapeEffectStats, ...] = field(default_factory=tuple)

    @property
    def totals(self) -> dict[str, int]:
        keys = list(_EFFECT_PATHS) + ["alpha_modifiers"]
        totals = {key: sum(getattr(slide, key) for slide in self.slides) for key in keys}
        totals["advanced_effects"] = sum(slide.advanced_effects for slide in self.slides)
        totals["slides_with_advanced_effects"] = sum(1 for slide in self.slides if slide.advanced_effects)
        totals["slides_with_alpha"] = sum(1 for slide in self.slides if slide.alpha_modifiers)
        totals["shapes_with_advanced_effects"] = sum(1 for shape in self.shapes if shape.advanced_effects)
        totals["shapes_with_alpha"] = sum(1 for shape in self.shapes if shape.alpha_modifiers)
        totals["slides"] = len(self.slides)
        return totals

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "totals": self.totals,
            "slides": [slide.to_dict() for slide in self.slides],
            "shapes": [shape.to_dict() for shape in self.shapes],
        }


def audit_pptx_effects(source: str | Path) -> PptxEffectAudit:
    """Conta efeitos DrawingML por slide e atribui efeitos aos shapes OOXML."""

    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pptx":
        raise ValueError("A auditoria de efeitos requer um arquivo .pptx.")

    stats: list[SlideEffectStats] = []
    shape_stats: list[ShapeEffectStats] = []
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
            shape_stats.extend(_shape_effect_stats(root, slide_number))
    return PptxEffectAudit(source=str(path), slides=tuple(stats), shapes=tuple(shape_stats))


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


def _shape_effect_stats(root: ET.Element, slide_number: int) -> list[ShapeEffectStats]:
    parent_by_child = {child: parent for parent in root.iter() for child in parent}
    counts_by_shape: dict[ET.Element, dict[str, int]] = {}

    def assign(element: ET.Element, key: str) -> None:
        owner = _nearest_shape(element, parent_by_child)
        if owner is None:
            return
        payload = counts_by_shape.setdefault(
            owner,
            {name: 0 for name in list(_EFFECT_PATHS) + ["alpha_modifiers"]},
        )
        payload[key] += 1

    for key, xpath in _EFFECT_PATHS.items():
        for element in root.findall(xpath, _NS):
            assign(element, key)
    for tag in _ALPHA_TAGS:
        for element in root.findall(f".//a:{tag}", _NS):
            assign(element, "alpha_modifiers")

    result: list[ShapeEffectStats] = []
    for shape, counts in counts_by_shape.items():
        shape_id, shape_name, shape_kind = _shape_identity(shape)
        result.append(
            ShapeEffectStats(
                slide=slide_number,
                shape_id=shape_id,
                shape_name=shape_name,
                shape_kind=shape_kind,
                **counts,
            )
        )
    result.sort(key=lambda item: (_shape_sort_id(item.shape_id), item.shape_kind, item.shape_name))
    return result


def _nearest_shape(element: ET.Element, parent_by_child: dict[ET.Element, ET.Element]) -> ET.Element | None:
    current = parent_by_child.get(element)
    while current is not None:
        if current.tag in _SHAPE_TAGS:
            return current
        current = parent_by_child.get(current)
    return None


def _shape_identity(shape: ET.Element) -> tuple[str, str, str]:
    kind = _SHAPE_TAGS.get(shape.tag, "shape")
    path = _CNVPR_PATHS.get(kind, "")
    c_nv_pr = shape.find(path, _NS) if path else None
    if c_nv_pr is None:
        return "", "", kind
    return str(c_nv_pr.get("id") or ""), str(c_nv_pr.get("name") or ""), kind


def _shape_sort_id(value: str) -> tuple[int, str]:
    try:
        return int(value), value
    except (TypeError, ValueError):
        return 2**31 - 1, str(value or "")


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-pptx-effects",
        description="Audita gradientes, transparência, sombras e demais efeitos DrawingML de um PPTX.",
    )
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path, help="Grava o relatório completo em JSON.")
    parser.add_argument("--slides", action="store_true", help="Exibe também os slides que possuem efeitos avançados.")
    parser.add_argument("--shapes", action="store_true", help="Exibe os shapes OOXML responsáveis pelos efeitos.")
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
        f"alpha={totals['alpha_modifiers']} "
        f"shapes={totals['shapes_with_advanced_effects']}"
    )
    if args.slides:
        for slide in report.slides:
            if slide.advanced_effects or slide.alpha_modifiers:
                print(
                    f"slide {slide.slide}: advanced={slide.advanced_effects} "
                    f"gradients={slide.gradient_fills} shadows={slide.outer_shadows + slide.inner_shadows} "
                    f"alpha={slide.alpha_modifiers}"
                )
    if args.shapes:
        for shape in report.shapes:
            if shape.advanced_effects or shape.alpha_modifiers:
                identity = shape.shape_name or shape.shape_id or "sem nome"
                print(
                    f"slide {shape.slide} shape {shape.shape_id or '?'} {identity}: "
                    f"advanced={shape.advanced_effects} gradients={shape.gradient_fills} "
                    f"shadows={shape.outer_shadows + shape.inner_shadows} alpha={shape.alpha_modifiers}"
                )
    if args.json_path:
        target = args.json_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
