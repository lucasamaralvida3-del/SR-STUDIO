from __future__ import annotations

"""Recuperação exata de letter/line spacing DrawingML para SR Scene.

Esta passagem pertence exclusivamente ao Graphics2. Ela não altera o leitor PPTX
compartilhado do SR Studio. O objetivo é complementar a importação com contratos
OOXML que afetam diretamente métricas tipográficas e que agora são medidos pelo
Production Gate.

A recuperação é deliberadamente conservadora: um valor só é aplicado quando o
shape fonte possui um contrato uniforme e existe um único node TEXT correspondente
na página. Shapes com múltiplos valores por run/parágrafo permanecem sem uma
simplificação falsa e são reportados como ambíguos.

Unidades persistidas:
- ``letter_spacing_pt``: pontos, igual ao contrato DrawingML ``spc / 100``;
- ``letter_spacing``: pixels lógicos (96 dpi), consumidos pelo Qt Quick/QPainter;
- ``line_spacing_pt`` + ``line_spacing_px`` para ``spcPts``;
- ``line_spacing_percent`` em escala percentual (100 = 100%) para ``spcPct``.

Essas chaves espelham o contrato de ``pptx_structure`` e evitam que auditoria e
renderer discordem sobre uma importação visualmente correta.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import math
import re
import zipfile

from xml.etree import ElementTree as ET

from .model import GraphicsDocument, GraphicsNode, NodeKind
from .pptx_text_content import recover_pptx_text_content

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS = {"a": _A, "p": _P}
_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_PT_TO_PX = 96.0 / 72.0


@dataclass(slots=True, frozen=True)
class PptxSpacingIssue:
    code: str
    slide: int
    shape_id: str
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxSpacingRecoveryReport:
    source_shapes: int = 0
    mapped_shapes: int = 0
    letter_spacing_shapes: int = 0
    line_spacing_shapes: int = 0
    letter_spacing_applied: int = 0
    line_spacing_applied: int = 0
    issues: list[PptxSpacingIssue] = field(default_factory=list)

    @property
    def letter_spacing_coverage(self) -> float:
        return 1.0 if self.letter_spacing_shapes == 0 else self.letter_spacing_applied / self.letter_spacing_shapes

    @property
    def line_spacing_coverage(self) -> float:
        return 1.0 if self.line_spacing_shapes == 0 else self.line_spacing_applied / self.line_spacing_shapes

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_shapes": self.source_shapes,
            "mapped_shapes": self.mapped_shapes,
            "letter_spacing_shapes": self.letter_spacing_shapes,
            "line_spacing_shapes": self.line_spacing_shapes,
            "letter_spacing_applied": self.letter_spacing_applied,
            "line_spacing_applied": self.line_spacing_applied,
            "letter_spacing_coverage": self.letter_spacing_coverage,
            "line_spacing_coverage": self.line_spacing_coverage,
            "issues": [item.to_dict() for item in self.issues],
        }


@dataclass(slots=True, frozen=True)
class _ShapeSpacing:
    slide: int
    shape_id: str
    shape_name: str
    letter_spacing: float | None
    line_spacing_percent: float | None
    line_spacing_pt: float | None
    letter_ambiguous: bool = False
    line_ambiguous: bool = False

    @property
    def has_letter_spacing(self) -> bool:
        return self.letter_spacing is not None or self.letter_ambiguous

    @property
    def has_line_spacing(self) -> bool:
        return self.line_spacing_percent is not None or self.line_spacing_pt is not None or self.line_ambiguous


def recover_pptx_spacing(source: str | Path, document: GraphicsDocument) -> PptxSpacingRecoveryReport:
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pptx":
        raise ValueError("Recuperação de spacing requer um arquivo .pptx.")

    # O leitor legado normaliza texto antes da SR Scene existir. O passe de
    # spacing já é executado para toda importação PPTX, portanto é o ponto mais
    # estreito para restaurar o contrato textual OOXML sem duplicar o pipeline.
    recover_pptx_text_content(path, document)

    contracts = _read_contracts(path)
    report = PptxSpacingRecoveryReport(source_shapes=len(contracts))

    for contract in contracts:
        if contract.has_letter_spacing:
            report.letter_spacing_shapes += 1
        if contract.has_line_spacing:
            report.line_spacing_shapes += 1

        if contract.slide <= 0 or contract.slide > len(document.pages):
            report.issues.append(_issue("PPTX_SPACING_PAGE_MISSING", contract, f"Slide {contract.slide} não existe na SR Scene."))
            continue
        page = document.pages[contract.slide - 1]
        candidates = _text_candidates(page.nodes.values(), contract.shape_name)
        if len(candidates) != 1:
            code = "PPTX_SPACING_SHAPE_AMBIGUOUS" if candidates else "PPTX_SPACING_SHAPE_MISSING"
            report.issues.append(
                _issue(
                    code,
                    contract,
                    f"Shape '{contract.shape_name or contract.shape_id}' possui {len(candidates)} candidato(s) TEXT na SR Scene; spacing não foi adivinhado.",
                )
            )
            continue

        node = candidates[0]
        report.mapped_shapes += 1
        node.metadata["pptx_shape_id"] = node.metadata.get("pptx_shape_id") or contract.shape_id
        node.metadata["pptx_shape_name"] = node.metadata.get("pptx_shape_name") or contract.shape_name
        spacing_meta = dict(node.metadata.get("pptx_spacing") or {})

        if contract.letter_ambiguous:
            node.style.pop("letter_spacing", None)
            node.style.pop("letter_spacing_pt", None)
            spacing_meta.pop("letter_spacing_pt", None)
            spacing_meta.pop("letter_spacing_px", None)
            spacing_meta["letter_spacing_mixed"] = True
            report.issues.append(_issue("PPTX_LETTER_SPACING_MIXED", contract, "Shape usa múltiplos valores de letter spacing; SR Scene não simplificou o conteúdo."))
        elif contract.letter_spacing is not None:
            points = float(contract.letter_spacing)
            pixels = points * _PT_TO_PX
            node.style["letter_spacing_pt"] = points
            node.style["letter_spacing"] = pixels
            spacing_meta.pop("letter_spacing_mixed", None)
            spacing_meta["letter_spacing_pt"] = points
            spacing_meta["letter_spacing_px"] = pixels
            report.letter_spacing_applied += 1

        if contract.line_ambiguous:
            node.style.pop("line_spacing_percent", None)
            node.style.pop("line_spacing_pt", None)
            node.style.pop("line_spacing_px", None)
            spacing_meta.pop("line_spacing_percent", None)
            spacing_meta.pop("line_spacing_pt", None)
            spacing_meta.pop("line_spacing_px", None)
            spacing_meta["line_spacing_mixed"] = True
            report.issues.append(_issue("PPTX_LINE_SPACING_MIXED", contract, "Shape usa múltiplos contratos de line spacing; SR Scene não simplificou o conteúdo."))
        elif contract.line_spacing_percent is not None:
            percent = float(contract.line_spacing_percent)
            node.style["line_spacing_percent"] = percent
            node.style.pop("line_spacing_pt", None)
            node.style.pop("line_spacing_px", None)
            spacing_meta.pop("line_spacing_mixed", None)
            spacing_meta.pop("line_spacing_pt", None)
            spacing_meta.pop("line_spacing_px", None)
            spacing_meta["line_spacing_percent"] = percent
            report.line_spacing_applied += 1
        elif contract.line_spacing_pt is not None:
            points = float(contract.line_spacing_pt)
            pixels = points * _PT_TO_PX
            node.style["line_spacing_pt"] = points
            node.style["line_spacing_px"] = pixels
            node.style.pop("line_spacing_percent", None)
            spacing_meta.pop("line_spacing_mixed", None)
            spacing_meta.pop("line_spacing_percent", None)
            spacing_meta["line_spacing_pt"] = points
            spacing_meta["line_spacing_px"] = pixels
            report.line_spacing_applied += 1

        if spacing_meta:
            node.metadata["pptx_spacing"] = spacing_meta
            node.metadata["pptx_enhanced"] = True

    document.metadata["pptx_spacing_recovery"] = report.to_dict()
    return report


def _read_contracts(path: Path) -> list[_ShapeSpacing]:
    contracts: list[_ShapeSpacing] = []
    with zipfile.ZipFile(path) as archive:
        entries: list[tuple[int, str]] = []
        for name in archive.namelist():
            match = _SLIDE_RE.match(name)
            if match:
                entries.append((int(match.group(1)), name))
        for slide, name in sorted(entries):
            root = ET.fromstring(archive.read(name))
            for shape in root.findall(".//p:sp", _NS):
                tx_body = shape.find("./p:txBody", _NS)
                if tx_body is None:
                    continue
                shape_id, shape_name = _shape_identity(shape)
                letter_values = _letter_values(tx_body)
                line_values = _line_values(tx_body)
                if not letter_values and not line_values:
                    continue
                letter_value, letter_ambiguous = _uniform(letter_values)
                line_value, line_ambiguous = _uniform(line_values)
                percent: float | None = None
                points: float | None = None
                if line_value is not None:
                    kind, value = line_value
                    if kind == "percent":
                        percent = value
                    else:
                        points = value
                contracts.append(
                    _ShapeSpacing(
                        slide=slide,
                        shape_id=shape_id,
                        shape_name=shape_name,
                        letter_spacing=letter_value,
                        line_spacing_percent=percent,
                        line_spacing_pt=points,
                        letter_ambiguous=letter_ambiguous,
                        line_ambiguous=line_ambiguous,
                    )
                )
    return contracts


def _shape_identity(shape: ET.Element) -> tuple[str, str]:
    c_nv_pr = shape.find("./p:nvSpPr/p:cNvPr", _NS)
    if c_nv_pr is None:
        return "", ""
    return str(c_nv_pr.get("id") or ""), str(c_nv_pr.get("name") or "")


def _letter_values(tx_body: ET.Element) -> list[float]:
    values: list[float] = []
    for xpath in (".//a:rPr[@spc]", ".//a:defRPr[@spc]", ".//a:endParaRPr[@spc]"):
        for item in tx_body.findall(xpath, _NS):
            raw = item.get("spc")
            if raw in (None, ""):
                continue
            try:
                values.append(int(raw) / 100.0)
            except ValueError:
                continue
    return _dedupe(values)


def _line_values(tx_body: ET.Element) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for ln_spc in tx_body.findall(".//a:pPr/a:lnSpc", _NS):
        pct = ln_spc.find("./a:spcPct", _NS)
        pts = ln_spc.find("./a:spcPts", _NS)
        if pct is not None and pct.get("val") not in (None, ""):
            try:
                values.append(("percent", int(pct.get("val")) / 1000.0))
            except ValueError:
                pass
        elif pts is not None and pts.get("val") not in (None, ""):
            try:
                values.append(("pt", int(pts.get("val")) / 100.0))
            except ValueError:
                pass
    return _dedupe_pairs(values)


def _uniform(values):
    if not values:
        return None, False
    if len(values) == 1:
        return values[0], False
    return None, True


def _text_candidates(nodes, shape_name: str) -> list[GraphicsNode]:
    target = _normal(shape_name)
    if not target:
        return []
    source_matches = [
        node for node in nodes
        if node.kind is NodeKind.TEXT and _normal((node.metadata or {}).get("source_name")) == target
    ]
    if source_matches:
        return source_matches
    return [node for node in nodes if node.kind is NodeKind.TEXT and _normal(node.name) == target]


def _dedupe(values: list[float]) -> list[float]:
    result: list[float] = []
    for value in values:
        if not any(math.isclose(value, current, rel_tol=1e-9, abs_tol=1e-6) for current in result):
            result.append(value)
    return result


def _dedupe_pairs(values: list[tuple[str, float]]) -> list[tuple[str, float]]:
    result: list[tuple[str, float]] = []
    for kind, value in values:
        if not any(kind == old_kind and math.isclose(value, old_value, rel_tol=1e-9, abs_tol=1e-6) for old_kind, old_value in result):
            result.append((kind, value))
    return result


def _issue(code: str, contract: _ShapeSpacing, message: str) -> PptxSpacingIssue:
    return PptxSpacingIssue(code, contract.slide, contract.shape_id, contract.shape_name, message)


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())
