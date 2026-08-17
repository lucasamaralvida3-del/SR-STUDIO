from __future__ import annotations

"""Atribuição scene-aware para regiões de divergência do Visual Fidelity Lab.

O ``fidelity_triage`` responde onde a imagem candidata diverge do Golden Master.
Este módulo cruza essas regiões com a geometria canônica da SR Scene para indicar
quais nós provavelmente explicam cada erro, sem alterar o score PASS/FAIL.
"""

from dataclasses import asdict, dataclass
from typing import Any
import math

from .fidelity_triage import FidelityRegion, FidelityTriageReport
from .model import BindingRole, GraphicsNode, GraphicsPage, NodeKind


@dataclass(slots=True, frozen=True)
class FidelityNodeSuspect:
    node_id: str
    name: str
    kind: str
    binding_role: str
    overlap_pixels: int
    region_overlap_ratio: float
    node_overlap_ratio: float
    score: float
    z_index: int
    rotated: bool
    diagnostic_hint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class FidelityRegionAttribution:
    region_index: int
    region: FidelityRegion
    suspects: tuple[FidelityNodeSuspect, ...]

    @property
    def matched(self) -> bool:
        return bool(self.suspects)

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_index": self.region_index,
            "region": self.region.to_dict(),
            "suspects": [item.to_dict() for item in self.suspects],
        }


@dataclass(slots=True, frozen=True)
class FidelityAttributionReport:
    page_id: str
    page_name: str
    page_width: float
    page_height: float
    image_width: int
    image_height: int
    regions: tuple[FidelityRegionAttribution, ...]

    @property
    def unmatched_regions(self) -> int:
        return sum(1 for item in self.regions if not item.matched)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "page_name": self.page_name,
            "page_width": self.page_width,
            "page_height": self.page_height,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "unmatched_regions": self.unmatched_regions,
            "regions": [item.to_dict() for item in self.regions],
        }


def attribute_fidelity_regions(
    report: FidelityTriageReport,
    page: GraphicsPage,
    *,
    max_suspects_per_region: int = 5,
    min_region_overlap_ratio: float = 0.01,
) -> FidelityAttributionReport:
    """Relaciona cada região de diff aos nós visíveis que a interceptam.

    A conversão respeita dimensões diferentes entre SR Scene e imagem renderizada.
    AABB de nós rotacionados é calculada após escala/pivô/rotação para que a triagem
    não perca elementos inclinados. Grupos e backgrounds continuam elegíveis, mas
    recebem peso menor para não encobrir texto, preço e imagem semanticamente úteis.
    """

    if page.width <= 0 or page.height <= 0:
        raise ValueError("A página precisa ter largura e altura positivas para atribuição de fidelidade.")
    if report.width <= 0 or report.height <= 0:
        raise ValueError("O relatório de fidelidade precisa ter dimensões de imagem positivas.")

    limit = max(1, int(max_suspects_per_region))
    minimum = max(0.0, min(1.0, float(min_region_overlap_ratio)))
    scale_x = report.width / float(page.width)
    scale_y = report.height / float(page.height)

    attributed: list[FidelityRegionAttribution] = []
    visible_nodes = [node for node in page.nodes.values() if node.visible and node.opacity > 0.0]

    for index, region in enumerate(report.regions, start=1):
        region_box = (
            float(region.x),
            float(region.y),
            float(region.x + region.width),
            float(region.y + region.height),
        )
        region_area = max(1.0, float(region.width * region.height))
        suspects: list[FidelityNodeSuspect] = []

        for node in visible_nodes:
            page_box = _node_page_bounds(node)
            pixel_box = (
                page_box[0] * scale_x,
                page_box[1] * scale_y,
                page_box[2] * scale_x,
                page_box[3] * scale_y,
            )
            overlap = _intersection_area(region_box, pixel_box)
            if overlap <= 0.0:
                continue

            region_ratio = overlap / region_area
            if region_ratio < minimum:
                continue

            node_area = max(1.0, (pixel_box[2] - pixel_box[0]) * (pixel_box[3] - pixel_box[1]))
            node_ratio = min(1.0, overlap / node_area)
            role = _enum_value(node.binding_role)
            kind = _enum_value(node.kind)
            score = _suspect_score(
                node=node,
                region_overlap_ratio=region_ratio,
                node_overlap_ratio=node_ratio,
            )
            suspects.append(
                FidelityNodeSuspect(
                    node_id=node.id,
                    name=node.name,
                    kind=kind,
                    binding_role=role,
                    overlap_pixels=max(1, int(round(overlap))),
                    region_overlap_ratio=region_ratio,
                    node_overlap_ratio=node_ratio,
                    score=score,
                    z_index=int(node.z_index),
                    rotated=not math.isclose(float(node.transform.rotation) % 360.0, 0.0, abs_tol=1e-9),
                    diagnostic_hint=_diagnostic_hint(node),
                )
            )

        suspects.sort(
            key=lambda item: (
                item.score,
                item.region_overlap_ratio,
                item.node_overlap_ratio,
                item.z_index,
                item.node_id,
            ),
            reverse=True,
        )
        attributed.append(
            FidelityRegionAttribution(
                region_index=index,
                region=region,
                suspects=tuple(suspects[:limit]),
            )
        )

    return FidelityAttributionReport(
        page_id=page.id,
        page_name=page.name,
        page_width=float(page.width),
        page_height=float(page.height),
        image_width=report.width,
        image_height=report.height,
        regions=tuple(attributed),
    )


def _node_page_bounds(node: GraphicsNode) -> tuple[float, float, float, float]:
    transform = node.transform
    x = float(transform.x)
    y = float(transform.y)
    width = float(transform.width)
    height = float(transform.height)
    pivot_x = x + width * float(transform.pivot_x)
    pivot_y = y + height * float(transform.pivot_y)
    scale_x = float(transform.scale_x)
    scale_y = float(transform.scale_y)
    angle = math.radians(float(transform.rotation))
    cosine = math.cos(angle)
    sine = math.sin(angle)

    points: list[tuple[float, float]] = []
    for px, py in ((x, y), (x + width, y), (x + width, y + height), (x, y + height)):
        sx = pivot_x + (px - pivot_x) * scale_x
        sy = pivot_y + (py - pivot_y) * scale_y
        dx = sx - pivot_x
        dy = sy - pivot_y
        rx = pivot_x + dx * cosine - dy * sine
        ry = pivot_y + dx * sine + dy * cosine
        points.append((rx, ry))

    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_x = max(point[0] for point in points)
    max_y = max(point[1] for point in points)
    return min_x, min_y, max_x, max_y


def _intersection_area(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _suspect_score(
    *,
    node: GraphicsNode,
    region_overlap_ratio: float,
    node_overlap_ratio: float,
) -> float:
    semantic_bonus = 0.10 if node.binding_role is not None else 0.0
    kind = node.kind
    if kind == NodeKind.BACKGROUND:
        kind_factor = 0.15
    elif kind == NodeKind.GROUP:
        kind_factor = 0.55
    elif kind == NodeKind.PRODUCT_CARD:
        kind_factor = 0.70
    elif kind in {NodeKind.TEXT, NodeKind.IMAGE, NodeKind.PATH}:
        kind_factor = 1.10
    else:
        kind_factor = 0.90

    base = (region_overlap_ratio * 0.68) + (node_overlap_ratio * 0.22) + semantic_bonus
    return base * kind_factor


def _diagnostic_hint(node: GraphicsNode) -> str:
    source_effects = dict((node.metadata or {}).get("pptx_effects") or {})
    effect_hint = _pptx_effect_hint(source_effects)
    role = node.binding_role
    if role in {
        BindingRole.CURRENCY,
        BindingRole.PRICE_REAIS,
        BindingRole.PRICE_CENTS,
        BindingRole.UNIT,
        BindingRole.APP_PRICE,
        BindingRole.WHOLESALE_PRICE,
        BindingRole.RETAIL_PRICE,
    }:
        base = "preço: revisar tipografia, baseline, alinhamento, auto-fit/wrap e formatação semântica"
    elif role == BindingRole.IMAGE or node.kind == NodeKind.IMAGE:
        base = "imagem: revisar asset, crop, fillRect, máscara, foco, zoom e fit mode"
    elif node.kind == NodeKind.TEXT:
        base = "texto: revisar fonte, métricas, spacing, alinhamento, wrap e auto-fit"
    elif node.kind == NodeKind.PATH:
        base = "vetor: revisar custGeom/path, stroke, fill, gradiente e efeitos"
    elif node.kind in {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.LINE}:
        base = "shape: revisar geometria, stroke, fill, gradiente, opacidade e efeitos"
    elif node.kind == NodeKind.PRODUCT_CARD:
        base = "ProductCard: revisar geometria e vínculos dos Smart Slots"
    elif node.kind == NodeKind.GROUP:
        base = "grupo: revisar transformações herdadas e geometria dos filhos"
    elif node.kind == NodeKind.BACKGROUND:
        base = "fundo: revisar cor, imagem de fundo, recorte e dimensões da página"
    else:
        base = "nó: revisar geometria, estilo e conteúdo"
    return f"{effect_hint}; {base}" if effect_hint else base


def _pptx_effect_hint(effects: dict[str, Any]) -> str:
    advanced = _as_int(effects.get("advanced_effects"))
    alpha = _as_int(effects.get("alpha_modifiers"))
    if advanced <= 0 and alpha <= 0:
        return ""
    gradients = _as_int(effects.get("gradient_fills"))
    shadows = _as_int(effects.get("outer_shadows")) + _as_int(effects.get("inner_shadows"))
    details: list[str] = []
    if gradients:
        details.append(f"{gradients} gradiente(s)")
    if shadows:
        details.append(f"{shadows} sombra(s)")
    if alpha:
        details.append(f"{alpha} alpha")
    if not details:
        details.append(f"{advanced} efeito(s) avançado(s)")
    return "efeitos PPTX: " + ", ".join(details) + " — validar reprodução no Golden Master"


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value))
