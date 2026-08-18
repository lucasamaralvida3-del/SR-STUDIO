from __future__ import annotations

"""Recuperação exata de ``a:stretch/a:fillRect`` DrawingML para SR Scene.

O leitor PPTX compartilhado já preserva ``fillRect`` na maioria dos casos, mas
uma auditoria baseada somente em contagem pode produzir falso 100% mesmo quando
os offsets foram alterados. Esta passagem pertence exclusivamente ao Graphics2:
relê os contratos OOXML, associa cada shape/picture à imagem correspondente na
SR Scene e materializa os quatro offsets exatos antes do Production Gate.

Valores DrawingML são armazenados como frações da caixa da forma (1.0 = 100%).
Isso preserva inclusive outsets negativos usados pelo Canva para estender uma
fotografia além da caixa antes do recorte visual.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import math
import zipfile

from srstudio.importers.pptx.package_order import ordered_slide_paths

from .image_fill import has_drawingml_fill_rect, normalize_fill_rect
from .model import GraphicsDocument, GraphicsNode, NodeKind
from .pptx_artwork import recover_pptx_artwork
from .pptx_image_transform import recover_pptx_image_transforms

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_KEYS = ("l", "t", "r", "b")


@dataclass(slots=True, frozen=True)
class PptxFillRectIssue:
    code: str
    slide: int
    shape_id: str
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class PptxFillRectContract:
    slide: int
    shape_id: str
    shape_name: str
    source_kind: str
    rect: dict[str, float]

    @property
    def has_outset(self) -> bool:
        return any(float(self.rect.get(key, 0.0)) < 0.0 for key in _KEYS)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["has_outset"] = self.has_outset
        return payload


@dataclass(slots=True)
class PptxFillRectRecoveryReport:
    source_contracts: int = 0
    mapped_contracts: int = 0
    exact_contracts: int = 0
    corrected_contracts: int = 0
    source_outsets: int = 0
    exact_outsets: int = 0
    issues: list[PptxFillRectIssue] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 1.0 if self.source_contracts == 0 else self.exact_contracts / self.source_contracts

    @property
    def outset_coverage(self) -> float:
        return 1.0 if self.source_outsets == 0 else self.exact_outsets / self.source_outsets

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_contracts": self.source_contracts,
            "mapped_contracts": self.mapped_contracts,
            "exact_contracts": self.exact_contracts,
            "corrected_contracts": self.corrected_contracts,
            "source_outsets": self.source_outsets,
            "exact_outsets": self.exact_outsets,
            "coverage": self.coverage,
            "outset_coverage": self.outset_coverage,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def recover_pptx_fill_rects(source: str | Path, document: GraphicsDocument) -> PptxFillRectRecoveryReport:
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pptx":
        raise ValueError("Recuperação de fillRect requer um arquivo .pptx.")

    # Artwork é recuperado antes dos contratos geométricos. Assim uma faixa,
    # fundo ou banner que tenha sido descartado na primeira passagem volta à SR
    # Scene a tempo de receber fillRect e rotação/flip exatos logo abaixo.
    _recover_artwork_contracts(path, document)

    contracts = _read_contracts(path)
    report = PptxFillRectRecoveryReport(
        source_contracts=len(contracts),
        source_outsets=sum(1 for contract in contracts if contract.has_outset),
    )

    for contract in contracts:
        if contract.slide <= 0 or contract.slide > len(document.pages):
            report.issues.append(_issue("PPTX_FILL_RECT_PAGE_MISSING", contract, f"Slide {contract.slide} não existe na SR Scene."))
            continue
        page = document.pages[contract.slide - 1]
        candidates = _image_candidates(page.nodes.values(), contract.shape_name)
        if len(candidates) != 1:
            code = "PPTX_FILL_RECT_SHAPE_AMBIGUOUS" if candidates else "PPTX_FILL_RECT_SHAPE_MISSING"
            report.issues.append(
                _issue(
                    code,
                    contract,
                    f"Imagem '{contract.shape_name or contract.shape_id}' possui {len(candidates)} candidato(s) na SR Scene; fillRect não foi adivinhado.",
                )
            )
            continue

        node = candidates[0]
        report.mapped_contracts += 1
        previous = normalize_fill_rect(node.style.get("fill_rect")) if has_drawingml_fill_rect(node.style.get("fill_rect")) else None
        if previous is None or not _rect_equal(previous, contract.rect):
            report.corrected_contracts += 1
            if previous is not None:
                node.metadata["pptx_fill_rect_previous"] = dict(previous)
        node.style["fill_rect"] = dict(contract.rect)
        node.metadata["pptx_shape_id"] = node.metadata.get("pptx_shape_id") or contract.shape_id
        node.metadata["pptx_shape_name"] = node.metadata.get("pptx_shape_name") or contract.shape_name
        node.metadata["pptx_fill_rect"] = {
            "source_kind": contract.source_kind,
            "rect": dict(contract.rect),
            "has_outset": contract.has_outset,
        }
        node.metadata["pptx_enhanced"] = True

        current = normalize_fill_rect(node.style.get("fill_rect"))
        if _rect_equal(current, contract.rect):
            report.exact_contracts += 1
            if contract.has_outset:
                report.exact_outsets += 1
        else:
            report.issues.append(_issue("PPTX_FILL_RECT_VALUE_MISMATCH", contract, "Offsets exatos não permaneceram na SR Scene após a recuperação."))

    document.metadata["pptx_fill_rect_recovery"] = report.to_dict()
    _recover_image_transform_contracts(path, document)
    return report


def _recover_artwork_contracts(path: Path, document: GraphicsDocument) -> None:
    """Recupera assets fixos sem transformar falha diagnóstica em crash."""

    try:
        recover_pptx_artwork(path, document)
    except Exception as exc:
        document.metadata["pptx_artwork_recovery"] = {
            "source_images": 0,
            "source_large_artworks": 0,
            "matched_images": 0,
            "recovered_nodes": 0,
            "repaired_assets": 0,
            "ready_images": 0,
            "ready_large_artworks": 0,
            "missing_media": 0,
            "ambiguous_images": 0,
            "coverage": 0.0,
            "large_artwork_coverage": 0.0,
            "issues": [],
            "error": str(exc),
        }


def _recover_image_transform_contracts(path: Path, document: GraphicsDocument) -> None:
    """Executa o segundo contrato de imagem sem tornar fillRect dependente dele."""

    try:
        recover_pptx_image_transforms(path, document)
    except Exception as exc:
        document.metadata["pptx_image_transform_recovery"] = {
            "source_contracts": 0,
            "non_identity_contracts": 0,
            "mapped_contracts": 0,
            "exact_contracts": 0,
            "exact_non_identity_contracts": 0,
            "corrected_contracts": 0,
            "composed_group_contracts": 0,
            "deferred_group_contracts": 0,
            "coverage": 0.0,
            "non_identity_coverage": 0.0,
            "issues": [],
            "error": str(exc),
        }


def _read_contracts(path: Path) -> list[PptxFillRectContract]:
    contracts: list[PptxFillRectContract] = []
    with zipfile.ZipFile(path) as archive:
        for slide, name in enumerate(ordered_slide_paths(archive), start=1):
            root = ET.fromstring(archive.read(name))
            for shape in root.findall(f".//{{{P_NS}}}sp"):
                if shape.find(f".//{{{A_NS}}}blip") is None:
                    continue
                fill_rect = shape.find(f".//{{{A_NS}}}stretch/{{{A_NS}}}fillRect")
                if fill_rect is None:
                    continue
                shape_id, shape_name = _shape_identity(shape, "sp")
                contracts.append(PptxFillRectContract(slide, shape_id, shape_name, "shape", _rect_percent(fill_rect)))
            for picture in root.findall(f".//{{{P_NS}}}pic"):
                fill_rect = picture.find(f".//{{{A_NS}}}stretch/{{{A_NS}}}fillRect")
                if fill_rect is None:
                    continue
                shape_id, shape_name = _shape_identity(picture, "pic")
                contracts.append(PptxFillRectContract(slide, shape_id, shape_name, "picture", _rect_percent(fill_rect)))
    return contracts


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


def _rect_percent(node: ET.Element) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in _KEYS:
        try:
            value = float(node.get(key, 0) or 0.0) / 100000.0
        except (TypeError, ValueError):
            value = 0.0
        result[key] = value if math.isfinite(value) else 0.0
    return result


def _rect_equal(left: dict[str, float], right: dict[str, float]) -> bool:
    a = normalize_fill_rect(left)
    b = normalize_fill_rect(right)
    return all(math.isclose(float(a[key]), float(b[key]), rel_tol=1e-9, abs_tol=1e-7) for key in _KEYS)


def _issue(code: str, contract: PptxFillRectContract, message: str) -> PptxFillRectIssue:
    return PptxFillRectIssue(code, contract.slide, contract.shape_id, contract.shape_name, message)


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())
