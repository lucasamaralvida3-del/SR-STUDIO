from __future__ import annotations

"""Compõe transforms de membros não-imagem dentro de grupos DrawingML.

O leitor PPTX legado já usa a matriz do grupo para obter o bounding box absoluto,
mas a rotação/flip persistidos no elemento continuam sendo apenas os do filho.
Para TEXT/SHAPE isso produz a posição correta com orientação errada. Esta passagem
recompõe pai + filho e materializa a Transform absoluta equivalente na SR Scene.

Assim como o contrato de imagens, composições que introduzem shear real são
reportadas e não recebem aproximação silenciosa.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import math
import zipfile

from srstudio.importers.pptx.package_order import ordered_slide_paths

from .model import GraphicsDocument, GraphicsNode, NodeKind

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_ANGLE_UNIT = 60000.0
_DEFAULT_SLIDE_WIDTH = 12192000.0
_DEFAULT_SLIDE_HEIGHT = 6858000.0
_SHEAR_TOLERANCE = 1e-7
_CANONICAL_ZERO_TOLERANCE = 1e-12


@dataclass(slots=True, frozen=True)
class _Affine:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def point(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f

    def vector(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.c * y, self.b * x + self.d * y

    def then(self, outer: "_Affine") -> "_Affine":
        return _Affine(
            a=outer.a * self.a + outer.c * self.b,
            b=outer.b * self.a + outer.d * self.b,
            c=outer.a * self.c + outer.c * self.d,
            d=outer.b * self.c + outer.d * self.d,
            e=outer.a * self.e + outer.c * self.f + outer.e,
            f=outer.b * self.e + outer.d * self.f + outer.f,
        )


@dataclass(slots=True, frozen=True)
class PptxGroupMemberTransformIssue:
    code: str
    slide: int
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class _Contract:
    slide: int
    shape_name: str
    source_center: tuple[float, float]
    axis_x: tuple[float, float]
    axis_y: tuple[float, float]
    source_width: float
    source_height: float


@dataclass(slots=True)
class PptxGroupMemberTransformReport:
    source_members: int = 0
    mapped_members: int = 0
    exact_members: int = 0
    corrected_members: int = 0
    deferred_shear_members: int = 0
    issues: list[PptxGroupMemberTransformIssue] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 1.0 if self.source_members == 0 else self.exact_members / self.source_members

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_members": self.source_members,
            "mapped_members": self.mapped_members,
            "exact_members": self.exact_members,
            "corrected_members": self.corrected_members,
            "deferred_shear_members": self.deferred_shear_members,
            "coverage": self.coverage,
            "issues": [item.to_dict() for item in self.issues],
        }


def recover_pptx_group_member_transforms(
    source: str | Path,
    document: GraphicsDocument,
) -> PptxGroupMemberTransformReport:
    path = Path(source)
    report = PptxGroupMemberTransformReport()
    if path.suffix.lower() != ".pptx" or not path.is_file():
        document.metadata["pptx_group_member_transform_recovery"] = report.to_dict()
        return report

    contracts, slide_width, slide_height = _read_contracts(path)
    report.source_members = len(contracts)
    for contract in contracts:
        if contract.slide <= 0 or contract.slide > len(document.pages):
            report.issues.append(
                _issue("PPTX_GROUP_MEMBER_PAGE_MISSING", contract, f"Slide {contract.slide} não existe na SR Scene.")
            )
            continue
        page = document.pages[contract.slide - 1]
        candidates = _candidates(page.nodes.values(), contract.shape_name)
        if len(candidates) != 1:
            code = "PPTX_GROUP_MEMBER_SHAPE_AMBIGUOUS" if candidates else "PPTX_GROUP_MEMBER_SHAPE_MISSING"
            report.issues.append(
                _issue(
                    code,
                    contract,
                    f"Membro agrupado '{contract.shape_name}' possui {len(candidates)} candidato(s) não-imagem na SR Scene; transform não foi adivinhada.",
                )
            )
            continue
        node = candidates[0]
        report.mapped_members += 1
        target = _target(contract, page.width, page.height, slide_width, slide_height)
        if target is None:
            report.deferred_shear_members += 1
            report.issues.append(
                _issue(
                    "PPTX_GROUP_MEMBER_SHEAR_DEFERRED",
                    contract,
                    "A composição pai/filho produz shear; Transform atual não representa matriz afim geral sem perda.",
                )
            )
            continue

        previous = {
            "x": float(node.transform.x),
            "y": float(node.transform.y),
            "width": float(node.transform.width),
            "height": float(node.transform.height),
            "rotation": float(node.transform.rotation),
            "scale_x": float(node.transform.scale_x),
            "scale_y": float(node.transform.scale_y),
        }
        if not _matches(node, target):
            node.metadata["pptx_group_member_transform_previous"] = previous
            report.corrected_members += 1

        node.transform.x = target["x"]
        node.transform.y = target["y"]
        node.transform.width = target["width"]
        node.transform.height = target["height"]
        node.transform.rotation = target["rotation"]
        node.transform.scale_x = -1.0 if target["flip_x"] else 1.0
        node.transform.scale_y = -1.0 if target["flip_y"] else 1.0
        node.metadata["pptx_group_member_transform"] = {
            "rotation": target["rotation"],
            "flip_x": target["flip_x"],
            "flip_y": target["flip_y"],
            "group_composed": True,
        }
        node.metadata["pptx_enhanced"] = True
        if _matches(node, target):
            report.exact_members += 1
        else:
            report.issues.append(
                _issue(
                    "PPTX_GROUP_MEMBER_TRANSFORM_VALUE_MISMATCH",
                    contract,
                    "Transform composta não permaneceu na SR Scene.",
                )
            )

    document.metadata["pptx_group_member_transform_recovery"] = report.to_dict()
    return report


def _read_contracts(path: Path) -> tuple[list[_Contract], float, float]:
    contracts: list[_Contract] = []
    with zipfile.ZipFile(path) as archive:
        slide_width, slide_height = _presentation_size(archive)
        for slide, slide_path in enumerate(ordered_slide_paths(archive), start=1):
            root = ET.fromstring(archive.read(slide_path))
            tree = root.find(f".//{{{P_NS}}}spTree")
            if tree is None:
                continue
            for child in list(tree):
                if _tag(child) == "grpSp":
                    _walk_group(child, slide, contracts, _Affine())
    return contracts, slide_width, slide_height


def _walk_group(
    group: ET.Element,
    slide: int,
    contracts: list[_Contract],
    parent: _Affine,
) -> None:
    group_xfrm = group.find(f"./{{{P_NS}}}grpSpPr/{{{A_NS}}}xfrm")
    combined = _group_affine(group_xfrm).then(parent)
    for child in list(group):
        tag = _tag(child)
        if tag == "grpSp":
            _walk_group(child, slide, contracts, combined)
            continue
        if tag != "sp":
            continue
        # Picture-filled p:sp é tratado pelo contrato IMAGE + compound text.
        if child.find(f".//{{{A_NS}}}blip") is not None:
            continue
        name = _shape_name(child)
        if not name:
            continue
        xfrm = child.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
        x, y, width, height = _geometry(xfrm)
        rotation, flip_x, flip_y = _orientation(xfrm)
        center = combined.point(x + width / 2.0, y + height / 2.0)
        own_x, own_y = _axes(rotation, flip_x, flip_y)
        contracts.append(
            _Contract(
                slide=slide,
                shape_name=name,
                source_center=center,
                axis_x=combined.vector(*own_x),
                axis_y=combined.vector(*own_y),
                source_width=width,
                source_height=height,
            )
        )


def _target(
    contract: _Contract,
    page_width: float,
    page_height: float,
    slide_width: float,
    slide_height: float,
) -> dict[str, float | bool] | None:
    sx = float(page_width) / max(1.0, float(slide_width))
    sy = float(page_height) / max(1.0, float(slide_height))
    ux = (contract.axis_x[0] * sx, contract.axis_x[1] * sy)
    uy = (contract.axis_y[0] * sx, contract.axis_y[1] * sy)
    norm_x = math.hypot(*ux)
    norm_y = math.hypot(*uy)
    if norm_x <= 1e-12 or norm_y <= 1e-12:
        return None
    orthogonality = abs(ux[0] * uy[0] + ux[1] * uy[1]) / (norm_x * norm_y)
    if orthogonality > _SHEAR_TOLERANCE:
        return None
    center_x = contract.source_center[0] * sx
    center_y = contract.source_center[1] * sy
    width = max(0.0, contract.source_width * norm_x)
    height = max(0.0, contract.source_height * norm_y)
    rotation = math.degrees(math.atan2(ux[1], ux[0]))
    determinant = ux[0] * uy[1] - ux[1] * uy[0]
    return {
        "x": _canonical_zero(center_x - width / 2.0),
        "y": _canonical_zero(center_y - height / 2.0),
        "width": _canonical_zero(width),
        "height": _canonical_zero(height),
        "rotation": _canonical_zero(rotation),
        "flip_x": False,
        "flip_y": determinant < 0.0,
    }


def _group_affine(xfrm: ET.Element | None) -> _Affine:
    if xfrm is None:
        return _Affine()
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    ch_off = xfrm.find(f"{{{A_NS}}}chOff")
    ch_ext = xfrm.find(f"{{{A_NS}}}chExt")
    ox = _float_attr(off, "x")
    oy = _float_attr(off, "y")
    ew = _float_attr(ext, "cx", 1.0)
    eh = _float_attr(ext, "cy", 1.0)
    cx = _float_attr(ch_off, "x")
    cy = _float_attr(ch_off, "y")
    cw = _float_attr(ch_ext, "cx", ew or 1.0)
    ch = _float_attr(ch_ext, "cy", eh or 1.0)
    scale_x = ew / max(cw, 1.0)
    scale_y = eh / max(ch, 1.0)
    base = _Affine(a=scale_x, d=scale_y, e=ox - cx * scale_x, f=oy - cy * scale_y)
    rotation, flip_x, flip_y = _orientation(xfrm)
    if _angle_equal(rotation, 0.0) and not flip_x and not flip_y:
        return base
    center_x = ox + ew / 2.0
    center_y = oy + eh / 2.0
    angle = math.radians(rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    fx = -1.0 if flip_x else 1.0
    fy = -1.0 if flip_y else 1.0
    around = _Affine(
        a=cos_a * fx,
        b=sin_a * fx,
        c=-sin_a * fy,
        d=cos_a * fy,
        e=center_x - (cos_a * fx) * center_x - (-sin_a * fy) * center_y,
        f=center_y - (sin_a * fx) * center_x - (cos_a * fy) * center_y,
    )
    return base.then(around)


def _axes(rotation: float, flip_x: bool, flip_y: bool) -> tuple[tuple[float, float], tuple[float, float]]:
    angle = math.radians(rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    fx = -1.0 if flip_x else 1.0
    fy = -1.0 if flip_y else 1.0
    return (cos_a * fx, sin_a * fx), (-sin_a * fy, cos_a * fy)


def _orientation(xfrm: ET.Element | None) -> tuple[float, bool, bool]:
    if xfrm is None:
        return 0.0, False, False
    try:
        rotation = float(xfrm.get("rot", 0) or 0.0) / _ANGLE_UNIT
    except (TypeError, ValueError):
        rotation = 0.0
    if not math.isfinite(rotation):
        rotation = 0.0
    return rotation, _bool_attr(xfrm, "flipH"), _bool_attr(xfrm, "flipV")


def _geometry(xfrm: ET.Element | None) -> tuple[float, float, float, float]:
    if xfrm is None:
        return 0.0, 0.0, 0.0, 0.0
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    return (
        _float_attr(off, "x"),
        _float_attr(off, "y"),
        max(0.0, _float_attr(ext, "cx")),
        max(0.0, _float_attr(ext, "cy")),
    )


def _candidates(nodes, shape_name: str) -> list[GraphicsNode]:
    target = _normal(shape_name)
    if not target:
        return []
    return [
        node
        for node in nodes
        if node.kind not in {NodeKind.GROUP, NodeKind.IMAGE, NodeKind.BACKGROUND}
        and not node.metadata.get("pptx_compound_owner_id")
        and _normal((node.metadata or {}).get("source_name") or node.name) == target
    ]


def _matches(node: GraphicsNode, target: dict[str, float | bool]) -> bool:
    return (
        _close(node.transform.x, target["x"])
        and _close(node.transform.y, target["y"])
        and _close(node.transform.width, target["width"])
        and _close(node.transform.height, target["height"])
        and _angle_equal(float(node.transform.rotation), float(target["rotation"]))
        and (float(node.transform.scale_x) < 0.0) == bool(target["flip_x"])
        and (float(node.transform.scale_y) < 0.0) == bool(target["flip_y"])
    )


def _shape_name(shape: ET.Element) -> str:
    node = shape.find(f"./{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
    return str(node.get("name") or "").strip() if node is not None else ""


def _presentation_size(archive: zipfile.ZipFile) -> tuple[float, float]:
    try:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
        node = root.find(f".//{{{P_NS}}}sldSz")
        if node is not None:
            width = _float_attr(node, "cx", _DEFAULT_SLIDE_WIDTH)
            height = _float_attr(node, "cy", _DEFAULT_SLIDE_HEIGHT)
            if width > 0.0 and height > 0.0:
                return width, height
    except (KeyError, ET.ParseError):
        pass
    return _DEFAULT_SLIDE_WIDTH, _DEFAULT_SLIDE_HEIGHT


def _float_attr(node: ET.Element | None, name: str, default: float = 0.0) -> float:
    if node is None:
        return float(default)
    try:
        value = float(node.get(name, default) or default)
    except (TypeError, ValueError):
        return float(default)
    return value if math.isfinite(value) else float(default)


def _bool_attr(node: ET.Element | None, name: str) -> bool:
    if node is None:
        return False
    return str(node.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _close(left: object, right: object) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-6)
    except (TypeError, ValueError):
        return False


def _canonical_zero(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        return value
    return 0.0 if abs(value) <= _CANONICAL_ZERO_TOLERANCE else value


def _angle_equal(left: float, right: float) -> bool:
    delta = (float(left) - float(right)) % 360.0
    return math.isclose(delta, 0.0, abs_tol=1e-7) or math.isclose(delta, 360.0, abs_tol=1e-7)


def _issue(code: str, contract: _Contract, message: str) -> PptxGroupMemberTransformIssue:
    return PptxGroupMemberTransformIssue(code, contract.slide, contract.shape_name, message)


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())
