from __future__ import annotations

"""Recupera o conteúdo textual DrawingML sem normalização destrutiva.

O leitor PPTX legado é deliberadamente simples e normaliza o texto com ``strip``.
Isso perde espaços significativos, parágrafos vazios e quebras ``a:br`` antes de a
SR Scene 2 existir. Esta passagem reabre o OOXML e restaura somente o contrato de
conteúdo quando existe um único node TEXT correspondente na página.

A recuperação não tenta modelar rich text por run; estilos continuam pertencendo
aos passes tipográficos existentes. O objetivo aqui é garantir que a Scene receba
os mesmos caracteres e limites de parágrafo declarados no PPTX.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET
import zipfile

from srstudio.importers.pptx.package_order import ordered_slide_paths

from .model import GraphicsDocument, GraphicsNode, NodeKind

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS = {"a": _A, "p": _P}


@dataclass(slots=True, frozen=True)
class PptxTextContentIssue:
    code: str
    slide: int
    shape_id: str
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class PptxTextContentContract:
    slide: int
    shape_id: str
    shape_name: str
    text: str
    paragraph_count: int
    empty_paragraphs: int
    inline_breaks: int
    tabs: int
    significant_boundary_whitespace: bool


@dataclass(slots=True)
class PptxTextContentRecoveryReport:
    source_contracts: int = 0
    mapped_contracts: int = 0
    exact_contracts: int = 0
    corrected_contracts: int = 0
    contracts_with_empty_paragraphs: int = 0
    contracts_with_inline_breaks: int = 0
    contracts_with_boundary_whitespace: int = 0
    issues: list[PptxTextContentIssue] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return 1.0 if self.source_contracts == 0 else self.exact_contracts / self.source_contracts

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_contracts": self.source_contracts,
            "mapped_contracts": self.mapped_contracts,
            "exact_contracts": self.exact_contracts,
            "corrected_contracts": self.corrected_contracts,
            "contracts_with_empty_paragraphs": self.contracts_with_empty_paragraphs,
            "contracts_with_inline_breaks": self.contracts_with_inline_breaks,
            "contracts_with_boundary_whitespace": self.contracts_with_boundary_whitespace,
            "coverage": self.coverage,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def recover_pptx_text_content(
    source: str | Path,
    document: GraphicsDocument,
) -> PptxTextContentRecoveryReport:
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".pptx":
        raise ValueError("Recuperação de conteúdo textual requer um arquivo .pptx.")

    contracts = _read_contracts(path)
    report = PptxTextContentRecoveryReport(
        source_contracts=len(contracts),
        contracts_with_empty_paragraphs=sum(1 for item in contracts if item.empty_paragraphs),
        contracts_with_inline_breaks=sum(1 for item in contracts if item.inline_breaks),
        contracts_with_boundary_whitespace=sum(1 for item in contracts if item.significant_boundary_whitespace),
    )

    for contract in contracts:
        if contract.slide <= 0 or contract.slide > len(document.pages):
            report.issues.append(
                _issue(
                    "PPTX_TEXT_CONTENT_PAGE_MISSING",
                    contract,
                    f"Slide {contract.slide} não existe na SR Scene.",
                )
            )
            continue

        page = document.pages[contract.slide - 1]
        candidates = _text_candidates(page.nodes.values(), contract.shape_name)
        if len(candidates) != 1:
            code = "PPTX_TEXT_CONTENT_SHAPE_AMBIGUOUS" if candidates else "PPTX_TEXT_CONTENT_SHAPE_MISSING"
            report.issues.append(
                _issue(
                    code,
                    contract,
                    f"Shape '{contract.shape_name or contract.shape_id}' possui {len(candidates)} candidato(s) TEXT na SR Scene; conteúdo não foi adivinhado.",
                )
            )
            continue

        node = candidates[0]
        report.mapped_contracts += 1
        previous = str(node.text or "")
        if previous != contract.text:
            node.metadata["pptx_text_content_previous"] = previous
            node.text = contract.text
            report.corrected_contracts += 1

        node.metadata["pptx_shape_id"] = node.metadata.get("pptx_shape_id") or contract.shape_id
        node.metadata["pptx_shape_name"] = node.metadata.get("pptx_shape_name") or contract.shape_name
        node.metadata["pptx_text_content"] = {
            "paragraph_count": contract.paragraph_count,
            "empty_paragraphs": contract.empty_paragraphs,
            "inline_breaks": contract.inline_breaks,
            "tabs": contract.tabs,
            "significant_boundary_whitespace": contract.significant_boundary_whitespace,
        }
        node.metadata["pptx_enhanced"] = True

        if str(node.text or "") == contract.text:
            report.exact_contracts += 1
        else:
            report.issues.append(
                _issue(
                    "PPTX_TEXT_CONTENT_VALUE_MISMATCH",
                    contract,
                    "Conteúdo OOXML exato não permaneceu na SR Scene após a recuperação.",
                )
            )

    document.metadata["pptx_text_content_recovery"] = report.to_dict()
    return report


def _read_contracts(path: Path) -> list[PptxTextContentContract]:
    contracts: list[PptxTextContentContract] = []
    with zipfile.ZipFile(path) as archive:
        for slide, name in enumerate(ordered_slide_paths(archive), start=1):
            root = ET.fromstring(archive.read(name))
            sp_tree = root.find(".//p:spTree", _NS)
            if sp_tree is None:
                continue
            _walk_shapes(sp_tree, slide, contracts)
    return contracts


def _walk_shapes(
    parent: ET.Element,
    slide: int,
    contracts: list[PptxTextContentContract],
) -> None:
    for child in list(parent):
        kind = _tag(child)
        if kind == "grpSp":
            _walk_shapes(child, slide, contracts)
            continue
        if kind != "sp":
            continue
        # Picture-filled shapes are single OOXML objects that materialize as an
        # IMAGE plus a recovered TEXT sibling. They have their own explicit
        # contract in pptx_compound_text; counting them here before that sibling
        # exists would create a false missing-text failure in this report.
        if child.find(".//a:blip", _NS) is not None:
            continue
        tx_body = child.find("./p:txBody", _NS)
        if tx_body is None:
            continue
        shape_id, shape_name = _shape_identity(child)
        paragraphs = tx_body.findall("./a:p", _NS)
        paragraph_texts: list[str] = []
        inline_breaks = 0
        tabs = 0
        for paragraph in paragraphs:
            text, breaks, paragraph_tabs = _paragraph_text(paragraph)
            paragraph_texts.append(text)
            inline_breaks += breaks
            tabs += paragraph_tabs
        text = "\n".join(paragraph_texts)
        contracts.append(
            PptxTextContentContract(
                slide=slide,
                shape_id=shape_id,
                shape_name=shape_name,
                text=text,
                paragraph_count=len(paragraphs),
                empty_paragraphs=sum(1 for item in paragraph_texts if item == ""),
                inline_breaks=inline_breaks,
                tabs=tabs,
                significant_boundary_whitespace=_has_boundary_whitespace(paragraph_texts),
            )
        )


def _paragraph_text(paragraph: ET.Element) -> tuple[str, int, int]:
    parts: list[str] = []
    breaks = 0
    tabs = 0
    for child in list(paragraph):
        kind = _tag(child)
        if kind in {"r", "fld"}:
            text_node = child.find("./a:t", _NS)
            if text_node is not None and text_node.text is not None:
                parts.append(text_node.text)
        elif kind == "br":
            parts.append("\n")
            breaks += 1
        elif kind == "tab":
            parts.append("\t")
            tabs += 1
    return "".join(parts), breaks, tabs


def _shape_identity(shape: ET.Element) -> tuple[str, str]:
    identity = shape.find("./p:nvSpPr/p:cNvPr", _NS)
    if identity is None:
        return "", ""
    return str(identity.get("id") or ""), str(identity.get("name") or "")


def _text_candidates(nodes: Iterable[GraphicsNode], shape_name: str) -> list[GraphicsNode]:
    nodes = list(nodes)
    target = _normal(shape_name)
    if not target:
        return []
    source_matches = [
        node
        for node in nodes
        if node.kind is NodeKind.TEXT and _normal((node.metadata or {}).get("source_name")) == target
    ]
    if source_matches:
        return source_matches
    return [node for node in nodes if node.kind is NodeKind.TEXT and _normal(node.name) == target]


def _has_boundary_whitespace(paragraphs: list[str]) -> bool:
    return any(text != text.strip() for text in paragraphs if text)


def _issue(
    code: str,
    contract: PptxTextContentContract,
    message: str,
) -> PptxTextContentIssue:
    return PptxTextContentIssue(code, contract.slide, contract.shape_id, contract.shape_name, message)


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())
