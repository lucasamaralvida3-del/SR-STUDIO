from __future__ import annotations

"""Recuperação exata de rotação/flip de imagens DrawingML para SR Scene.

A posição/caixa continua vindo do importador maduro do SR Studio. Esta segunda
passagem Graphics2 relê apenas o contrato visual do ``a:xfrm`` de cada imagem
(``p:sp`` com ``a:blipFill`` ou ``p:pic``), restaura rotação e espelhamento e
prova o resultado antes do Production Gate.

Transformações não triviais no grupo ancestral não são adivinhadas. Nesses casos
a importação mantém o conteúdo existente, registra um diagnóstico e não concede
cobertura exata até existir composição matricial dedicada no Graphics2.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import math
import re
import zipfile

from .model import GraphicsDocument, GraphicsNode, NodeKind

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_ANGLE_UNIT = 60000.0


@dataclass(slots=True, frozen=True)
class PptxImageTransformIssue:
    code: str
    slide: int
    shape_id: str
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class PptxImageTransformContract:
    slide: int
    shape_id: str
    shape_name: str
    source_kind: str
    rotation: float = 0.0
    flip_x: bool = False
    flip_y: bool = False
    transformed_group_ancestor: bool = False

    @property
    def non_identity(self) -> bool:
        return not _angle_equal(self.rotation, 0.0) or self.flip_x or self.flip_y

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["non_identity"] = self.non_identity
        return payload


@dataclass(slots=True)
class PptxImageTransformRecoveryReport:
    source_contracts: int = 0
    non_identity_contracts: int = 0
    mapped_contracts: int = 0
    exact_contracts: int = 0
    exact_non_identity_contracts: int = 0
    corrected_contracts: int = 0
    deferred_group_contracts: int = 0
    issues: list[PptxImageTransformIssue] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 1.0 if self.source_contracts == 0 else self.exact_contracts / self.source_contracts

    @property
    def non_identity_coverage(self) -> float:
        if self.non_identity_contracts == 0:
            return 1.0
        return self.exact_non_identity_contracts / self.non_identity_contracts

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_contracts": self.source_contracts,
            "non_identity_contracts": self.non_identity_contracts,
            "mapped_contracts": self.mapped_contracts,
            "exact_contracts": self.exact_contracts,
            "exact_non_identity_contracts": self.exact_non_identity_contracts,
            "corrected_contracts": self.corrected_contracts,
            "deferred_group_contracts": self.deferred_group_contracts,
            "coverage": self.coverage,
            "non_identity_coverage": self.non_identity_coverage,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def recover_pptx_image_transforms(
    source: str | Path,
    document: GraphicsDocument,
) -> PptxImageTransformRecoveryReport:
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pptx":
        raise ValueError("Recuperação de transformação de imagem requer um arquivo .pptx.")

    contracts = _read_contracts(path)
    report = PptxImageTransformRecoveryReport(
        source_contracts=len(contracts),
        non_identity_contracts=sum(1 for contract in contracts if contract.non_identity),
    )

    for contract in contracts:
        if contract.slide <= 0 or contract.slide > len(document.pages):
            report.issues.append(
                _issue(
                    "PPTX_IMAGE_TRANSFORM_PAGE_MISSING",
                    contract,
                    f"Slide {contract.slide} não existe na SR Scene.",
                )
            )
            continue
        page = document.pages[contract.slide - 1]
        candidates = _image_candidates(page.nodes.values(), contract.shape_name)
        if len(candidates) != 1:
            code = "PPTX_IMAGE_TRANSFORM_SHAPE_AMBIGUOUS" if candidates else "PPTX_IMAGE_TRANSFORM_SHAPE_MISSING"
            report.issues.append(
                _issue(
                    code,
                    contract,
                    f"Imagem '{contract.shape_name or contract.shape_id}' possui {len(candidates)} candidato(s) na SR Scene; transformação não foi adivinhada.",
                )
            )
            continue

        node = candidates[0]
        report.mapped_contracts += 1
        if contract.transformed_group_ancestor:
            report.deferred_group_contracts += 1
            report.issues.append(
                _issue(
                    "PPTX_IMAGE_TRANSFORM_GROUP_COMPOSITION_DEFERRED",
                    contract,
                    "Imagem pertence a grupo com rotação/flip; composição matricial exata ainda não foi aplicada.",
                )
            )
            continue

        previous = {
            "rotation": float(node.transform.rotation or 0.0),
            "flip_x": bool(node.style.get("flip_x")),
            "flip_y": bool(node.style.get("flip_y")),
        }
        changed = (
            not _angle_equal(previous["rotation"], contract.rotation)
            or previous["flip_x"] != contract.flip_x
            or previous["flip_y"] != contract.flip_y
        )
        if changed:
            report.corrected_contracts += 1
            node.metadata["pptx_image_transform_previous"] = previous

        node.transform.rotation = float(contract.rotation)
        node.style["flip_x"] = bool(contract.flip_x)
        node.style["flip_y"] = bool(contract.flip_y)
        node.metadata["pptx_shape_id"] = node.metadata.get("pptx_shape_id") or contract.shape_id
        node.metadata["pptx_shape_name"] = node.metadata.get("pptx_shape_name") or contract.shape_name
        node.metadata["pptx_image_transform"] = {
            "source_kind": contract.source_kind,
            "rotation": float(contract.rotation),
            "flip_x": bool(contract.flip_x),
            "flip_y": bool(contract.flip_y),
            "transformed_group_ancestor": False,
        }
        node.metadata["pptx_enhanced"] = True

        if _node_matches(node, contract):
            report.exact_contracts += 1
            if contract.non_identity:
                report.exact_non_identity_contracts += 1
        else:
            report.issues.append(
                _issue(
                    "PPTX_IMAGE_TRANSFORM_VALUE_MISMATCH",
                    contract,
                    "Rotação/flip exatos não permaneceram na SR Scene após a recuperação.",
                )
            )

    document.metadata["pptx_image_transform_recovery"] = report.to_dict()
    return report


def _read_contracts(path: Path) -> list[PptxImageTransformContract]:
    contracts: list[PptxImageTransformContract] = []
    with zipfile.ZipFile(path) as archive:
        slides: list[tuple[int, str]] = []
        for name in archive.namelist():
            match = _SLIDE_RE.match(name)
            if match:
                slides.append((int(match.group(1)), name))
        for slide, name in sorted(slides):
            root = ET.fromstring(archive.read(name))
            sp_tree = root.find(f".//{{{P_NS}}}spTree")
            if sp_tree is None:
                continue
            for child in list(sp_tree):
                _walk_node(child, slide, contracts, transformed_group=False)
    return contracts


def _walk_node(
    node: ET.Element,
    slide: int,
    contracts: list[PptxImageTransformContract],
    *,
    transformed_group: bool,
) -> None:
    kind = _tag(node)
    if kind == "grpSp":
        group_xfrm = node.find(f"./{{{P_NS}}}grpSpPr/{{{A_NS}}}xfrm")
        inherited = transformed_group or _xfrm_non_identity(group_xfrm)
        for child in list(node):
            if _tag(child) in {"grpSp", "sp", "pic"}:
                _walk_node(child, slide, contracts, transformed_group=inherited)
        return

    if kind == "sp" and node.find(f".//{{{A_NS}}}blip") is not None:
        shape_id, shape_name = _shape_identity(node, "sp")
        xfrm = node.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
        rotation, flip_x, flip_y = _xfrm_values(xfrm)
        contracts.append(
            PptxImageTransformContract(
                slide,
                shape_id,
                shape_name,
                "shape",
                rotation,
                flip_x,
                flip_y,
                transformed_group,
            )
        )
        return

    if kind == "pic":
        shape_id, shape_name = _shape_identity(node, "pic")
        xfrm = node.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
        rotation, flip_x, flip_y = _xfrm_values(xfrm)
        contracts.append(
            PptxImageTransformContract(
                slide,
                shape_id,
                shape_name,
                "picture",
                rotation,
                flip_x,
                flip_y,
                transformed_group,
            )
        )


def _xfrm_values(node: ET.Element | None) -> tuple[float, bool, bool]:
    if node is None:
        return 0.0, False, False
    try:
        rotation = float(node.get("rot", 0) or 0.0) / _ANGLE_UNIT
    except (TypeError, ValueError):
        rotation = 0.0
    if not math.isfinite(rotation):
        rotation = 0.0
    return rotation, _bool_attr(node, "flipH"), _bool_attr(node, "flipV")


def _xfrm_non_identity(node: ET.Element | None) -> bool:
    rotation, flip_x, flip_y = _xfrm_values(node)
    return not _angle_equal(rotation, 0.0) or flip_x or flip_y


def _shape_identity(node: ET.Element, kind: str) -> tuple[str, str]:
    path = f"./{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr" if kind == "sp" else f"./{{{P_NS}}}nvPicPr/{{{P_NS}}}cNvPr"
    identity = node.find(path)
    if identity is None:
        identity = node.find(f".//{{{P_NS}}}cNvPr")
    if identity is None:
        return "", ""
    return str(identity.get("id") or ""), str(identity.get("name") or "").strip()


def _image_candidates(nodes, shape_name: str) -> list[GraphicsNode]:
    target = _normal(shape_name)
    if not target:
        return []
    source_matches = [
        node
        for node in nodes
        if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}
        and _normal((node.metadata or {}).get("source_name")) == target
    ]
    if source_matches:
        return source_matches
    return [
        node
        for node in nodes
        if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND} and _normal(node.name) == target
    ]


def _node_matches(node: GraphicsNode, contract: PptxImageTransformContract) -> bool:
    return (
        _angle_equal(float(node.transform.rotation or 0.0), contract.rotation)
        and bool(node.style.get("flip_x")) == contract.flip_x
        and bool(node.style.get("flip_y")) == contract.flip_y
    )


def _angle_equal(left: float, right: float) -> bool:
    try:
        delta = (float(left) - float(right)) % 360.0
    except (TypeError, ValueError):
        return False
    return math.isclose(delta, 0.0, abs_tol=1e-7) or math.isclose(delta, 360.0, abs_tol=1e-7)


def _bool_attr(node: ET.Element, name: str) -> bool:
    return str(node.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _issue(
    code: str,
    contract: PptxImageTransformContract,
    message: str,
) -> PptxImageTransformIssue:
    return PptxImageTransformIssue(code, contract.slide, contract.shape_id, contract.shape_name, message)


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())
