from __future__ import annotations

"""Mapeia o inventário de efeitos DrawingML para nodes da SR Scene.

O importador legado já preserva ``source_name`` nos nodes do Graphics2. Esta
camada usa somente essa informação local, sem alterar o leitor PPTX compartilhado
do SR Studio. O mapeamento é deliberadamente conservador: nomes ambíguos nunca
são associados por adivinhação.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from .model import GraphicsDocument, GraphicsNode, NodeKind


@dataclass(slots=True, frozen=True)
class PptxEffectNodeMapping:
    slide: int
    shape_id: str
    shape_name: str
    node_id: str
    node_name: str
    advanced_effects: int
    alpha_modifiers: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class PptxEffectMappingIssue:
    code: str
    slide: int
    shape_id: str
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxEffectMappingReport:
    source_shapes: int = 0
    mapped_shapes: int = 0
    ambiguous_shapes: int = 0
    missing_shapes: int = 0
    mappings: list[PptxEffectNodeMapping] = field(default_factory=list)
    issues: list[PptxEffectMappingIssue] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        if self.source_shapes <= 0:
            return 1.0
        return self.mapped_shapes / self.source_shapes

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_shapes": self.source_shapes,
            "mapped_shapes": self.mapped_shapes,
            "ambiguous_shapes": self.ambiguous_shapes,
            "missing_shapes": self.missing_shapes,
            "coverage": self.coverage,
            "mappings": [item.to_dict() for item in self.mappings],
            "issues": [item.to_dict() for item in self.issues],
        }


def map_pptx_effects_to_document(document: GraphicsDocument) -> PptxEffectMappingReport:
    """Associa shapes do audit ``pptx_effects`` aos nodes importados por slide."""

    effects = dict(document.metadata.get("pptx_effects") or {})
    shapes = [dict(item) for item in effects.get("shapes") or [] if isinstance(item, dict)]
    report = PptxEffectMappingReport(source_shapes=len(shapes))

    for source in shapes:
        slide = _int(source.get("slide"))
        shape_id = str(source.get("shape_id") or "")
        shape_name = str(source.get("shape_name") or "").strip()
        if slide <= 0 or slide > len(document.pages):
            report.missing_shapes += 1
            report.issues.append(
                PptxEffectMappingIssue(
                    "PPTX_EFFECT_PAGE_MISSING",
                    slide,
                    shape_id,
                    shape_name,
                    f"Slide {slide} do shape com efeitos não existe na SR Scene.",
                )
            )
            continue

        page = document.pages[slide - 1]
        candidates = _named_candidates(page.nodes.values(), shape_name)
        candidates = _prefer_kind(candidates, str(source.get("shape_kind") or ""))
        if len(candidates) == 1:
            node = candidates[0]
            payload = dict(source)
            node.metadata["pptx_effects"] = payload
            node.metadata["pptx_shape_id"] = shape_id
            node.metadata["pptx_shape_name"] = shape_name
            report.mapped_shapes += 1
            report.mappings.append(
                PptxEffectNodeMapping(
                    slide=slide,
                    shape_id=shape_id,
                    shape_name=shape_name,
                    node_id=node.id,
                    node_name=node.name,
                    advanced_effects=_int(source.get("advanced_effects")),
                    alpha_modifiers=_int(source.get("alpha_modifiers")),
                )
            )
            continue

        if len(candidates) > 1:
            report.ambiguous_shapes += 1
            report.issues.append(
                PptxEffectMappingIssue(
                    "PPTX_EFFECT_SHAPE_AMBIGUOUS",
                    slide,
                    shape_id,
                    shape_name,
                    f"Shape '{shape_name or shape_id}' possui {len(candidates)} candidatos na SR Scene; associação não foi adivinhada.",
                )
            )
        else:
            report.missing_shapes += 1
            report.issues.append(
                PptxEffectMappingIssue(
                    "PPTX_EFFECT_SHAPE_MISSING",
                    slide,
                    shape_id,
                    shape_name,
                    f"Shape '{shape_name or shape_id}' com efeitos não foi localizado na SR Scene.",
                )
            )

    document.metadata["pptx_effect_mapping"] = report.to_dict()
    return report


def _named_candidates(nodes, shape_name: str) -> list[GraphicsNode]:
    target = _normal(shape_name)
    if not target:
        return []
    source_matches = [
        node
        for node in nodes
        if _normal((node.metadata or {}).get("source_name")) == target
    ]
    if source_matches:
        return source_matches
    return [node for node in nodes if _normal(node.name) == target]


def _prefer_kind(candidates: list[GraphicsNode], shape_kind: str) -> list[GraphicsNode]:
    if len(candidates) <= 1:
        return candidates
    source_kind = str(shape_kind or "").lower()
    if source_kind == "picture":
        preferred = [node for node in candidates if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}]
    elif source_kind == "graphic_frame":
        preferred = [node for node in candidates if node.kind not in {NodeKind.IMAGE, NodeKind.TEXT}]
    elif source_kind == "group":
        preferred = [node for node in candidates if node.kind is NodeKind.GROUP]
    else:
        preferred = [node for node in candidates if node.kind is not NodeKind.GROUP]
    return preferred or candidates


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
