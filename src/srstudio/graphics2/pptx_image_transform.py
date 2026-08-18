from __future__ import annotations

"""Recuperação exata de rotação/flip de imagens DrawingML para SR Scene.

A posição/caixa continua vindo do importador maduro do SR Studio para imagens
fora de grupos. Para imagens agrupadas, esta passagem recompõe a transformação
DrawingML completa (inclusive grupos aninhados) e materializa uma Transform
absoluta equivalente na SR Scene quando a composição não contém shear.

Quando escala anisotrópica + rotação produz shear, o Graphics2 não possui hoje
uma Transform afim geral capaz de representá-lo. O caso permanece explícito no
relatório em vez de receber uma aproximação silenciosa.
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
        """Return ``outer(self(point))``."""
        return _Affine(
            a=outer.a * self.a + outer.c * self.b,
            b=outer.b * self.a + outer.d * self.b,
            c=outer.a * self.c + outer.c * self.d,
            d=outer.b * self.c + outer.d * self.d,
            e=outer.a * self.e + outer.c * self.f + outer.e,
            f=outer.b * self.e + outer.d * self.f + outer.f,
        )


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
    grouped: bool = False
    source_center: tuple[float, float] = (0.0, 0.0)
    axis_x: tuple[float, float] = (1.0, 0.0)
    axis_y: tuple[float, float] = (0.0, 1.0)
    source_width: float = 0.0
    source_height: float = 0.0

    @property
    def non_identity(self) -> bool:
        return (
            not _angle_equal(self.rotation, 0.0)
            or self.flip_x
            or self.flip_y
            or self.transformed_group_ancestor
        )

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
    composed_group_contracts: int = 0
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
            "composed_group_contracts": self.composed_group_contracts,
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

    contracts, slide_width, slide_height = _read_contracts(path)
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
        target = _target_transform(contract, page.width, page.height, slide_width, slide_height)
        if target is None:
            report.deferred_group_contracts += 1
            report.issues.append(
                _issue(
                    "PPTX_IMAGE_TRANSFORM_GROUP_SHEAR_DEFERRED",
                    contract,
                    "A composição pai/filho produz shear (escala anisotrópica combinada com rotação); a SR Scene ainda não possui Transform afim geral para representá-lo sem perda.",
                )
            )
            continue

        previous = {
            "x": float(node.transform.x or 0.0),
            "y": float(node.transform.y or 0.0),
            "width": float(node.transform.width or 0.0),
            "height": float(node.transform.height or 0.0),
            "rotation": float(node.transform.rotation or 0.0),
            "flip_x": bool(node.style.get("flip_x")),
            "flip_y": bool(node.style.get("flip_y")),
        }
        changed = not _node_matches_target(node, target)
        if changed:
            report.corrected_contracts += 1
            node.metadata["pptx_image_transform_previous"] = previous

        if contract.grouped:
            node.transform.x = target["x"]
            node.transform.y = target["y"]
            node.transform.width = target["width"]
            node.transform.height = target["height"]
            report.composed_group_contracts += 1
        node.transform.rotation = target["rotation"]
        node.style["flip_x"] = target["flip_x"]
        node.style["flip_y"] = target["flip_y"]
        node.metadata["pptx_shape_id"] = node.metadata.get("pptx_shape_id") or contract.shape_id
        node.metadata["pptx_shape_name"] = node.metadata.get("pptx_shape_name") or contract.shape_name
        node.metadata["pptx_image_transform"] = {
            "source_kind": contract.source_kind,
            "source_rotation": float(contract.rotation),
            "source_flip_x": bool(contract.flip_x),
            "source_flip_y": bool(contract.flip_y),
            "rotation": float(target["rotation"]),
            "flip_x": bool(target["flip_x"]),
            "flip_y": bool(target["flip_y"]),
            "grouped": bool(contract.grouped),
            "group_composed": bool(contract.grouped),
            "transformed_group_ancestor": bool(contract.transformed_group_ancestor),
        }
        node.metadata["pptx_enhanced"] = True

        if _node_matches_target(node, target):
            report.exact_contracts += 1
            if contract.non_identity:
                report.exact_non_identity_contracts += 1
        else:
            report.issues.append(
                _issue(
                    "PPTX_IMAGE_TRANSFORM_VALUE_MISMATCH",
                    contract,
                    "Transformação exata não permaneceu na SR Scene após a recuperação.",
                )
            )

    document.metadata["pptx_image_transform_recovery"] = report.to_dict()
    return report


def _read_contracts(path: Path) -> tuple[list[PptxImageTransformContract], float, float]:
    contracts: list[PptxImageTransformContract] = []
    with zipfile.ZipFile(path) as archive:
        slide_width, slide_height = _presentation_size(archive)
        for slide, name in enumerate(ordered_slide_paths(archive), start=1):
            root = ET.fromstring(archive.read(name))
            sp_tree = root.find(f".//{{{P_NS}}}spTree")
            if sp_tree is None:
                continue
            for child in list(sp_tree):
                _walk_node(
                    child,
                    slide,
                    contracts,
                    parent=_Affine(),
                    grouped=False,
                    transformed_group=False,
                )
    return contracts, slide_width, slide_height


def _walk_node(
    node: ET.Element,
    slide: int,
    contracts: list[PptxImageTransformContract],
    *,
    parent: _Affine,
    grouped: bool,
    transformed_group: bool,
) -> None:
    kind = _tag(node)
    if kind == "grpSp":
        group_xfrm = node.find(f"./{{{P_NS}}}grpSpPr/{{{A_NS}}}xfrm")
        group = _group_affine(group_xfrm)
        inherited_transform = transformed_group or _xfrm_orientation_non_identity(group_xfrm)
        combined = group.then(parent)
        for child in list(node):
            if _tag(child) in {"grpSp", "sp", "pic"}:
                _walk_node(
                    child,
                    slide,
                    contracts,
                    parent=combined,
                    grouped=True,
                    transformed_group=inherited_transform,
                )
        return

    if kind == "sp" and node.find(f".//{{{A_NS}}}blip") is not None:
        shape_id, shape_name = _shape_identity(node, "sp")
        xfrm = node.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
        contracts.append(
            _contract(
                slide,
                shape_id,
                shape_name,
                "shape",
                xfrm,
                parent,
                grouped=grouped,
                transformed_group=transformed_group,
            )
        )
        return

    if kind == "pic":
        shape_id, shape_name = _shape_identity(node, "pic")
        xfrm = node.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
        contracts.append(
            _contract(
                slide,
                shape_id,
                shape_name,
                "picture",
                xfrm,
                parent,
                grouped=grouped,
                transformed_group=transformed_group,
            )
        )


def _contract(
    slide: int,
    shape_id: str,
    shape_name: str,
    source_kind: str,
    xfrm: ET.Element | None,
    parent: _Affine,
    *,
    grouped: bool,
    transformed_group: bool,
) -> PptxImageTransformContract:
    rotation, flip_x, flip_y = _xfrm_values(xfrm)
    x, y, width, height = _xfrm_geometry(xfrm)
    center = parent.point(x + width / 2.0, y + height / 2.0)
    own_x, own_y = _orientation_axes(rotation, flip_x, flip_y)
    axis_x = parent.vector(*own_x)
    axis_y = parent.vector(*own_y)
    return PptxImageTransformContract(
        slide=slide,
        shape_id=shape_id,
        shape_name=shape_name,
        source_kind=source_kind,
        rotation=rotation,
        flip_x=flip_x,
        flip_y=flip_y,
        transformed_group_ancestor=transformed_group,
        grouped=grouped,
        source_center=center,
        axis_x=axis_x,
        axis_y=axis_y,
        source_width=width,
        source_height=height,
    )


def _target_transform(
    contract: PptxImageTransformContract,
    page_width: float,
    page_height: float,
    slide_width: float,
    slide_height: float,
) -> dict[str, float | bool] | None:
    if not contract.grouped:
        return {
            "x": 0.0,
            "y": 0.0,
            "width": 0.0,
            "height": 0.0,
            "rotation": float(contract.rotation),
            "flip_x": bool(contract.flip_x),
            "flip_y": bool(contract.flip_y),
            "apply_geometry": False,
        }

    scale_x = float(page_width) / max(1.0, float(slide_width))
    scale_y = float(page_height) / max(1.0, float(slide_height))
    ux = (contract.axis_x[0] * scale_x, contract.axis_x[1] * scale_y)
    uy = (contract.axis_y[0] * scale_x, contract.axis_y[1] * scale_y)
    norm_x = math.hypot(*ux)
    norm_y = math.hypot(*uy)
    if norm_x <= 1e-12 or norm_y <= 1e-12:
        return None
    orthogonality = abs(ux[0] * uy[0] + ux[1] * uy[1]) / (norm_x * norm_y)
    if orthogonality > _SHEAR_TOLERANCE:
        return None

    center_x = contract.source_center[0] * scale_x
    center_y = contract.source_center[1] * scale_y
    width = max(0.0, contract.source_width * norm_x)
    height = max(0.0, contract.source_height * norm_y)
    rotation = math.degrees(math.atan2(ux[1], ux[0]))
    determinant = ux[0] * uy[1] - ux[1] * uy[0]
    # Decomposição canônica: o eixo X define a rotação; eventual reflexão fica
    # no eixo Y. É visualmente equivalente à matriz DrawingML completa e evita
    # ambiguidades de decomposição (R+flipH == R+180+flipV).
    flip_x = False
    flip_y = determinant < 0.0
    return {
        "x": center_x - width / 2.0,
        "y": center_y - height / 2.0,
        "width": width,
        "height": height,
        "rotation": rotation,
        "flip_x": flip_x,
        "flip_y": flip_y,
        "apply_geometry": True,
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
    sx = ew / max(cw, 1.0)
    sy = eh / max(ch, 1.0)
    base = _Affine(a=sx, d=sy, e=ox - cx * sx, f=oy - cy * sy)
    rotation, flip_x, flip_y = _xfrm_values(xfrm)
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


def _orientation_axes(rotation: float, flip_x: bool, flip_y: bool) -> tuple[tuple[float, float], tuple[float, float]]:
    angle = math.radians(rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    fx = -1.0 if flip_x else 1.0
    fy = -1.0 if flip_y else 1.0
    return (cos_a * fx, sin_a * fx), (-sin_a * fy, cos_a * fy)


def _xfrm_geometry(node: ET.Element | None) -> tuple[float, float, float, float]:
    if node is None:
        return 0.0, 0.0, 0.0, 0.0
    off = node.find(f"{{{A_NS}}}off")
    ext = node.find(f"{{{A_NS}}}ext")
    return (
        _float_attr(off, "x"),
        _float_attr(off, "y"),
        max(0.0, _float_attr(ext, "cx")),
        max(0.0, _float_attr(ext, "cy")),
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


def _xfrm_orientation_non_identity(node: ET.Element | None) -> bool:
    rotation, flip_x, flip_y = _xfrm_values(node)
    return not _angle_equal(rotation, 0.0) or flip_x or flip_y


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


def _node_matches_target(node: GraphicsNode, target: dict[str, float | bool]) -> bool:
    if not _angle_equal(float(node.transform.rotation or 0.0), float(target["rotation"])):
        return False
    if bool(node.style.get("flip_x")) != bool(target["flip_x"]):
        return False
    if bool(node.style.get("flip_y")) != bool(target["flip_y"]):
        return False
    if not bool(target.get("apply_geometry")):
        return True
    return (
        _close(node.transform.x, target["x"])
        and _close(node.transform.y, target["y"])
        and _close(node.transform.width, target["width"])
        and _close(node.transform.height, target["height"])
    )


def _close(left: object, right: object) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-6)
    except (TypeError, ValueError):
        return False


def _angle_equal(left: float, right: float) -> bool:
    try:
        delta = (float(left) - float(right)) % 360.0
    except (TypeError, ValueError):
        return False
    return math.isclose(delta, 0.0, abs_tol=1e-7) or math.isclose(delta, 360.0, abs_tol=1e-7)


def _bool_attr(node: ET.Element | None, name: str) -> bool:
    if node is None:
        return False
    return str(node.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _float_attr(node: ET.Element | None, name: str, default: float = 0.0) -> float:
    if node is None:
        return float(default)
    try:
        value = float(node.get(name, default) or default)
    except (TypeError, ValueError):
        return float(default)
    return value if math.isfinite(value) else float(default)


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
