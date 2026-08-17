from __future__ import annotations

"""Auditoria estrutural OOXML para importações PPTX/Canva.

Mede a estrutura fonte antes da conversão e compara o que chegou ao SR Scene.
Além de páginas, imagens, grupos e auto-fit, os contratos tipográficos de
espaçamento são comparados pelo valor original da shape para evitar falsos 100%.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import json
import math
import re
import sys
import zipfile

from .image_fill import has_drawingml_fill_rect, normalize_fill_rect
from .model import GraphicsDocument, NodeKind

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

_CURRENCY_RE = re.compile(r"^R\s*\$$", re.IGNORECASE)
_INTEGER_RE = re.compile(r"^\d{1,3}$")
_CENTS_RE = re.compile(r"^[,.]\d{1,2}$")
_UNIT_RE = re.compile(r"^/?(?:KG|UN|UND|G|L|ML|LT|CX|PCT|PC|BDJ)$", re.IGNORECASE)


@dataclass(slots=True)
class PptxSlideStructure:
    slide: int
    shapes: int = 0
    text_shapes: int = 0
    shape_autofit: int = 0
    normal_autofit: int = 0
    no_autofit: int = 0
    letter_spacing_contracts: list[dict[str, Any]] = field(default_factory=list)
    line_spacing_contracts: list[dict[str, Any]] = field(default_factory=list)
    pictures: int = 0
    image_fill_shapes: int = 0
    image_fill_rects: int = 0
    image_fill_outsets: int = 0
    groups: int = 0
    custom_geometry: int = 0
    image_custom_geometry: int = 0
    currency_tokens: int = 0
    integer_tokens: int = 0
    cents_tokens: int = 0
    unit_tokens: int = 0
    estimated_split_prices: int = 0
    image_fill_shape_names: list[str] = field(default_factory=list)

    @property
    def autofit_contracts(self) -> int:
        return self.shape_autofit + self.normal_autofit + self.no_autofit

    @property
    def letter_spacing_count(self) -> int:
        return len(self.letter_spacing_contracts)

    @property
    def line_spacing_count(self) -> int:
        return len(self.line_spacing_contracts)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["autofit_contracts"] = self.autofit_contracts
        payload["letter_spacing_count"] = self.letter_spacing_count
        payload["line_spacing_count"] = self.line_spacing_count
        return payload


@dataclass(slots=True)
class PptxMappingAudit:
    source_slides: int = 0
    imported_pages: int = 0
    source_text_shapes: int = 0
    imported_text_nodes: int = 0
    source_autofit_contracts: int = 0
    imported_autofit_contracts: int = 0
    source_shape_autofit: int = 0
    imported_shape_autofit: int = 0
    source_normal_autofit: int = 0
    imported_normal_autofit: int = 0
    source_no_autofit: int = 0
    imported_no_autofit: int = 0
    source_letter_spacing_contracts: int = 0
    imported_letter_spacing_contracts: int = 0
    source_line_spacing_contracts: int = 0
    imported_line_spacing_contracts: int = 0
    source_image_shapes: int = 0
    imported_image_nodes: int = 0
    source_groups: int = 0
    imported_group_nodes: int = 0
    source_fill_rects: int = 0
    imported_fill_rects: int = 0
    source_fill_outsets: int = 0
    imported_fill_outsets: int = 0
    source_image_custom_geometry: int = 0
    imported_image_clips: int = 0
    page_count_match: bool = True
    text_coverage: float = 1.0
    autofit_coverage: float = 1.0
    shape_autofit_coverage: float = 1.0
    normal_autofit_coverage: float = 1.0
    no_autofit_coverage: float = 1.0
    letter_spacing_coverage: float = 1.0
    line_spacing_coverage: float = 1.0
    image_coverage: float = 1.0
    group_coverage: float = 1.0
    fill_rect_coverage: float = 1.0
    fill_outset_coverage: float = 1.0
    image_clip_coverage: float = 1.0
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxStructureReport:
    source_name: str = ""
    source_sha256: str = ""
    source_size: int = 0
    slide_count: int = 0
    slide_width_emu: int = 0
    slide_height_emu: int = 0
    shapes: int = 0
    text_shapes: int = 0
    shape_autofit: int = 0
    normal_autofit: int = 0
    no_autofit: int = 0
    letter_spacing_contracts: list[dict[str, Any]] = field(default_factory=list)
    line_spacing_contracts: list[dict[str, Any]] = field(default_factory=list)
    pictures: int = 0
    image_fill_shapes: int = 0
    image_fill_rects: int = 0
    image_fill_outsets: int = 0
    groups: int = 0
    custom_geometry: int = 0
    image_custom_geometry: int = 0
    estimated_split_prices: int = 0
    slides: list[PptxSlideStructure] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def autofit_contracts(self) -> int:
        return self.shape_autofit + self.normal_autofit + self.no_autofit

    @property
    def letter_spacing_count(self) -> int:
        return len(self.letter_spacing_contracts)

    @property
    def line_spacing_count(self) -> int:
        return len(self.line_spacing_contracts)

    @property
    def ready(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["autofit_contracts"] = self.autofit_contracts
        payload["letter_spacing_count"] = self.letter_spacing_count
        payload["line_spacing_count"] = self.line_spacing_count
        return payload

    def audit_document(self, document: GraphicsDocument) -> PptxMappingAudit:
        imported_text = sum(
            1
            for page in document.pages
            for node in page.nodes.values()
            if node.kind is NodeKind.TEXT and str(node.text or "").strip()
        )
        imported_shape_autofit = sum(
            1
            for page in document.pages
            for node in page.nodes.values()
            if node.kind is NodeKind.TEXT and str(node.style.get("pptx_auto_fit") or "").lower() == "shape"
        )
        imported_normal_autofit = sum(
            1
            for page in document.pages
            for node in page.nodes.values()
            if node.kind is NodeKind.TEXT and str(node.style.get("pptx_auto_fit") or "").lower() == "normal"
        )
        imported_no_autofit = sum(
            1
            for page in document.pages
            for node in page.nodes.values()
            if node.kind is NodeKind.TEXT and str(node.style.get("pptx_auto_fit") or "").lower() == "none"
        )
        imported_autofit = imported_shape_autofit + imported_normal_autofit + imported_no_autofit
        imported_letter_spacing = _matching_spacing_contracts(
            document,
            self.letter_spacing_contracts,
            letter_spacing=True,
        )
        imported_line_spacing = _matching_spacing_contracts(
            document,
            self.line_spacing_contracts,
            letter_spacing=False,
        )
        imported_images = sum(
            1
            for page in document.pages
            for node in page.nodes.values()
            if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}
        )
        imported_groups = sum(
            1
            for page in document.pages
            for node in page.nodes.values()
            if node.kind is NodeKind.GROUP
        )
        imported_fill_rects = 0
        imported_fill_outsets = 0
        imported_image_clips = 0
        for page in document.pages:
            for node in page.nodes.values():
                if node.kind not in {NodeKind.IMAGE, NodeKind.BACKGROUND}:
                    continue
                fill_rect = node.style.get("fill_rect")
                if has_drawingml_fill_rect(fill_rect):
                    imported_fill_rects += 1
                    if any(value < 0.0 for value in normalize_fill_rect(fill_rect).values()):
                        imported_fill_outsets += 1
                if isinstance(node.metadata.get("clip_path"), dict):
                    imported_image_clips += 1

        source_images = self.pictures + self.image_fill_shapes
        type_coverages = [
            _coverage(imported_shape_autofit, self.shape_autofit) if self.shape_autofit else 1.0,
            _coverage(imported_normal_autofit, self.normal_autofit) if self.normal_autofit else 1.0,
            _coverage(imported_no_autofit, self.no_autofit) if self.no_autofit else 1.0,
        ]
        audit = PptxMappingAudit(
            source_slides=self.slide_count,
            imported_pages=len(document.pages),
            source_text_shapes=self.text_shapes,
            imported_text_nodes=imported_text,
            source_autofit_contracts=self.autofit_contracts,
            imported_autofit_contracts=imported_autofit,
            source_shape_autofit=self.shape_autofit,
            imported_shape_autofit=imported_shape_autofit,
            source_normal_autofit=self.normal_autofit,
            imported_normal_autofit=imported_normal_autofit,
            source_no_autofit=self.no_autofit,
            imported_no_autofit=imported_no_autofit,
            source_letter_spacing_contracts=self.letter_spacing_count,
            imported_letter_spacing_contracts=imported_letter_spacing,
            source_line_spacing_contracts=self.line_spacing_count,
            imported_line_spacing_contracts=imported_line_spacing,
            source_image_shapes=source_images,
            imported_image_nodes=imported_images,
            source_groups=self.groups,
            imported_group_nodes=imported_groups,
            source_fill_rects=self.image_fill_rects,
            imported_fill_rects=imported_fill_rects,
            source_fill_outsets=self.image_fill_outsets,
            imported_fill_outsets=imported_fill_outsets,
            source_image_custom_geometry=self.image_custom_geometry,
            imported_image_clips=imported_image_clips,
            page_count_match=len(document.pages) == self.slide_count,
            text_coverage=_coverage(imported_text, self.text_shapes),
            autofit_coverage=min(type_coverages) if self.autofit_contracts else 1.0,
            shape_autofit_coverage=_coverage(imported_shape_autofit, self.shape_autofit),
            normal_autofit_coverage=_coverage(imported_normal_autofit, self.normal_autofit),
            no_autofit_coverage=_coverage(imported_no_autofit, self.no_autofit),
            letter_spacing_coverage=_coverage(imported_letter_spacing, self.letter_spacing_count),
            line_spacing_coverage=_coverage(imported_line_spacing, self.line_spacing_count),
            image_coverage=_coverage(imported_images, source_images),
            group_coverage=_coverage(imported_groups, self.groups),
            fill_rect_coverage=_coverage(imported_fill_rects, self.image_fill_rects),
            fill_outset_coverage=_coverage(imported_fill_outsets, self.image_fill_outsets),
            image_clip_coverage=_coverage(imported_image_clips, self.image_custom_geometry),
        )
        if not audit.page_count_match:
            audit.warnings.append(
                f"PPTX possui {self.slide_count} slide(s), mas o SR Scene importou {len(document.pages)} página(s)."
            )
        if self.text_shapes >= 4 and audit.text_coverage < 0.90:
            audit.warnings.append(
                f"Cobertura de texto PPTX baixa: {audit.text_coverage * 100:.2f}% "
                f"({imported_text}/{self.text_shapes})."
            )
        if self.autofit_contracts >= 4 and audit.autofit_coverage < 0.95:
            audit.warnings.append(
                f"Cobertura de contratos auto-fit PPTX baixa: {audit.autofit_coverage * 100:.2f}% "
                f"({imported_autofit}/{self.autofit_contracts}); verifique spAutoFit/normAutofit/noAutofit."
            )
        if self.letter_spacing_count >= 4 and audit.letter_spacing_coverage < 0.95:
            audit.warnings.append(
                f"Cobertura de letter spacing PPTX baixa: {audit.letter_spacing_coverage * 100:.2f}% "
                f"({imported_letter_spacing}/{self.letter_spacing_count}) com valor preservado."
            )
        if self.line_spacing_count >= 4 and audit.line_spacing_coverage < 0.95:
            audit.warnings.append(
                f"Cobertura de line spacing PPTX baixa: {audit.line_spacing_coverage * 100:.2f}% "
                f"({imported_line_spacing}/{self.line_spacing_count}) com valor preservado."
            )
        if source_images >= 2 and audit.image_coverage < 0.85:
            audit.warnings.append(
                f"Cobertura de imagens PPTX baixa: {audit.image_coverage * 100:.2f}% "
                f"({imported_images}/{source_images}). Verifique p:sp/a:blipFill."
            )
        if self.groups >= 2 and audit.group_coverage < 0.50:
            audit.warnings.append(
                f"Cobertura de grupos DrawingML baixa: {audit.group_coverage * 100:.2f}% "
                f"({imported_groups}/{self.groups})."
            )
        if self.image_fill_rects and audit.fill_rect_coverage < 0.95:
            audit.warnings.append(
                f"Cobertura de stretch/fillRect DrawingML baixa: {audit.fill_rect_coverage * 100:.2f}% "
                f"({imported_fill_rects}/{self.image_fill_rects})."
            )
        if self.image_fill_outsets and audit.fill_outset_coverage < 0.95:
            audit.warnings.append(
                f"Cobertura de fillRect com outset negativo baixa: {audit.fill_outset_coverage * 100:.2f}% "
                f"({imported_fill_outsets}/{self.image_fill_outsets})."
            )
        if self.image_custom_geometry and audit.image_clip_coverage < 0.95:
            audit.warnings.append(
                f"Cobertura de máscaras custGeom irregulares em imagens baixa: {audit.image_clip_coverage * 100:.2f}% "
                f"({imported_image_clips}/{self.image_custom_geometry})."
            )
        return audit


def inspect_pptx_structure(source: str | Path) -> PptxStructureReport:
    path = Path(source)
    report = PptxStructureReport(source_name=path.name)
    if path.suffix.lower() != ".pptx" or not path.is_file():
        report.warnings.append(f"PPTX não encontrado: {path}")
        return report

    raw = path.read_bytes()
    report.source_size = len(raw)
    report.source_sha256 = sha256(raw).hexdigest()
    try:
        with zipfile.ZipFile(path) as archive:
            report.slide_width_emu, report.slide_height_emu = _presentation_size(archive)
            slides = sorted(
                (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=_slide_number,
            )
            report.slide_count = len(slides)
            for slide_path in slides:
                slide_no = _slide_number(slide_path)
                try:
                    root = ET.fromstring(archive.read(slide_path))
                except (KeyError, ET.ParseError) as exc:
                    report.warnings.append(f"{slide_path}: XML inválido ({exc}).")
                    continue
                item = _inspect_slide(root, slide_no)
                report.slides.append(item)
                report.shapes += item.shapes
                report.text_shapes += item.text_shapes
                report.shape_autofit += item.shape_autofit
                report.normal_autofit += item.normal_autofit
                report.no_autofit += item.no_autofit
                report.letter_spacing_contracts.extend(item.letter_spacing_contracts)
                report.line_spacing_contracts.extend(item.line_spacing_contracts)
                report.pictures += item.pictures
                report.image_fill_shapes += item.image_fill_shapes
                report.image_fill_rects += item.image_fill_rects
                report.image_fill_outsets += item.image_fill_outsets
                report.groups += item.groups
                report.custom_geometry += item.custom_geometry
                report.image_custom_geometry += item.image_custom_geometry
                report.estimated_split_prices += item.estimated_split_prices
    except (OSError, zipfile.BadZipFile) as exc:
        report.warnings.append(f"Não foi possível abrir o PPTX: {exc}")
    return report


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-pptx-structure",
        description="Audita a estrutura OOXML de um PPTX/Canva antes da conversão para SR Scene 2.",
    )
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path, default=None, help="Salva o relatório JSON neste caminho.")
    parser.add_argument("--slides", action="store_true", help="Exibe também a contagem por slide.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = inspect_pptx_structure(args.pptx)
    payload = report.to_dict()
    if args.json_path:
        target = Path(args.json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "SR PPTX Structure: "
        f"slides={report.slide_count} · textos={report.text_shapes} · "
        f"autofit={report.autofit_contracts} "
        f"(forma={report.shape_autofit}, texto={report.normal_autofit}, sem={report.no_autofit}) · "
        f"letterSpacing={report.letter_spacing_count} · lineSpacing={report.line_spacing_count} · "
        f"imagens={report.pictures + report.image_fill_shapes} "
        f"(pic={report.pictures}, blipFill={report.image_fill_shapes}) · "
        f"fillRect={report.image_fill_rects} (outset={report.image_fill_outsets}) · "
        f"máscaras irregulares={report.image_custom_geometry} · grupos={report.groups} · "
        f"custGeom={report.custom_geometry} · preços~={report.estimated_split_prices}"
    )
    print(f"SHA-256: {report.source_sha256 or '-'}")
    if args.slides:
        for slide in report.slides:
            print(
                f"  slide {slide.slide}: shapes={slide.shapes} textos={slide.text_shapes} "
                f"autofit={slide.autofit_contracts} "
                f"(forma={slide.shape_autofit}, texto={slide.normal_autofit}, sem={slide.no_autofit}) "
                f"letterSpacing={slide.letter_spacing_count} lineSpacing={slide.line_spacing_count} "
                f"imagens={slide.pictures + slide.image_fill_shapes} grupos={slide.groups} "
                f"custGeom={slide.custom_geometry} fillRect={slide.image_fill_rects} "
                f"outset={slide.image_fill_outsets} máscaras irregulares={slide.image_custom_geometry} "
                f"preços~={slide.estimated_split_prices}"
            )
    for warning in report.warnings:
        print(f"AVISO: {warning}", file=sys.stderr)
    return 0 if report.ready else 1


def _inspect_slide(root: ET.Element, slide_no: int) -> PptxSlideStructure:
    item = PptxSlideStructure(slide=slide_no)
    currencies = integers = cents = units = 0
    for shape in root.findall(f".//{{{P_NS}}}sp"):
        item.shapes += 1
        name = _shape_name(shape)
        text = _shape_text(shape)
        if text:
            item.text_shapes += 1
            body = shape.find(f"./{{{P_NS}}}txBody/{{{A_NS}}}bodyPr")
            if body is not None:
                if body.find(f"{{{A_NS}}}spAutoFit") is not None:
                    item.shape_autofit += 1
                elif body.find(f"{{{A_NS}}}normAutofit") is not None:
                    item.normal_autofit += 1
                elif body.find(f"{{{A_NS}}}noAutofit") is not None:
                    item.no_autofit += 1
            letter = _source_letter_spacing(shape)
            if letter is not None:
                item.letter_spacing_contracts.append(
                    {"slide": slide_no, "shape_name": name, "unit": "pt", "value": letter}
                )
            line = _source_line_spacing(shape)
            if line is not None:
                unit, value = line
                item.line_spacing_contracts.append(
                    {"slide": slide_no, "shape_name": name, "unit": unit, "value": value}
                )
            cleaned = _clean_text(text)
            currencies += int(bool(_CURRENCY_RE.fullmatch(cleaned)))
            integers += int(bool(_INTEGER_RE.fullmatch(cleaned)))
            cents += int(bool(_CENTS_RE.fullmatch(cleaned)))
            units += int(bool(_UNIT_RE.fullmatch(cleaned)))

        has_image_fill = shape.find(f".//{{{A_NS}}}blip") is not None
        custom = shape.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}custGeom")
        has_custom_geometry = custom is not None
        if has_image_fill:
            item.image_fill_shapes += 1
            if name:
                item.image_fill_shape_names.append(name)
            fill_rect = shape.find(f".//{{{A_NS}}}stretch/{{{A_NS}}}fillRect")
            if fill_rect is not None:
                item.image_fill_rects += 1
                if any(value < 0.0 for value in _rect_percent(fill_rect).values()):
                    item.image_fill_outsets += 1
            if _custom_geometry_requires_clip(custom):
                item.image_custom_geometry += 1
        if has_custom_geometry:
            item.custom_geometry += 1

    pictures = root.findall(f".//{{{P_NS}}}pic")
    item.pictures = len(pictures)
    for picture in pictures:
        fill_rect = picture.find(f".//{{{A_NS}}}stretch/{{{A_NS}}}fillRect")
        if fill_rect is not None:
            item.image_fill_rects += 1
            if any(value < 0.0 for value in _rect_percent(fill_rect).values()):
                item.image_fill_outsets += 1
        custom = picture.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}custGeom")
        if _custom_geometry_requires_clip(custom):
            item.image_custom_geometry += 1

    item.groups = len(root.findall(f".//{{{P_NS}}}grpSp"))
    item.currency_tokens = currencies
    item.integer_tokens = integers
    item.cents_tokens = cents
    item.unit_tokens = units
    item.estimated_split_prices = min(currencies, integers, cents, units)
    return item


def _source_letter_spacing(shape: ET.Element) -> float | None:
    for path in (f".//{{{A_NS}}}rPr", f".//{{{A_NS}}}defRPr"):
        node = shape.find(path)
        if node is None or node.get("spc") in (None, ""):
            continue
        try:
            return float(node.get("spc") or 0) / 100.0
        except (TypeError, ValueError):
            return None
    return None


def _source_line_spacing(shape: ET.Element) -> tuple[str, float] | None:
    paragraph = shape.find(f".//{{{A_NS}}}pPr")
    if paragraph is None:
        return None
    line_spacing = paragraph.find(f"{{{A_NS}}}lnSpc")
    if line_spacing is None or not len(line_spacing):
        return None
    child = list(line_spacing)[0]
    kind = child.tag.rsplit("}", 1)[-1]
    try:
        numeric = float(child.get("val") or 0)
    except (TypeError, ValueError):
        return None
    if kind == "spcPts":
        return "pt", numeric / 100.0
    if kind == "spcPct":
        return "percent", numeric / 1000.0
    return None


def _matching_spacing_contracts(
    document: GraphicsDocument,
    contracts: list[dict[str, Any]],
    *,
    letter_spacing: bool,
) -> int:
    matches = 0
    for contract in contracts:
        slide = _int(contract.get("slide"))
        name = str(contract.get("shape_name") or "")
        if slide <= 0 or slide > len(document.pages) or not name:
            continue
        page = document.pages[slide - 1]
        candidates = [
            node
            for node in page.nodes.values()
            if node.kind is NodeKind.TEXT and str(node.metadata.get("source_name") or node.name or "") == name
        ]
        if any(_node_spacing_matches(node.style, contract, letter_spacing=letter_spacing) for node in candidates):
            matches += 1
    return matches


def _node_spacing_matches(style: dict[str, Any], contract: dict[str, Any], *, letter_spacing: bool) -> bool:
    try:
        expected = float(contract.get("value"))
    except (TypeError, ValueError):
        return False
    unit = str(contract.get("unit") or "")
    if letter_spacing:
        raw = style.get("letter_spacing_pt")
    elif unit == "pt":
        raw = style.get("line_spacing_pt")
    elif unit == "percent":
        raw = style.get("line_spacing_percent")
    else:
        return False
    try:
        actual = float(raw)
    except (TypeError, ValueError):
        return False
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6)


def _custom_geometry_requires_clip(custom: ET.Element | None) -> bool:
    if custom is None:
        return False
    path_list = custom.find(f"{{{A_NS}}}pathLst")
    if path_list is None:
        return True
    paths = path_list.findall(f"{{{A_NS}}}path")
    if len(paths) != 1:
        return True
    path = paths[0]
    width = _number(path.get("w"))
    height = _number(path.get("h"))
    if width <= 0 or height <= 0:
        return True
    points: list[tuple[float, float]] = []
    for command in list(path):
        tag = command.tag.rsplit("}", 1)[-1]
        if tag in {"moveTo", "lnTo"}:
            point = command.find(f".//{{{A_NS}}}pt")
            if point is None:
                return True
            points.append((round(_number(point.get("x")), 3), round(_number(point.get("y")), 3)))
        elif tag == "close":
            continue
        else:
            return True
    if len(points) not in {4, 5}:
        return True
    expected = {
        (0.0, 0.0),
        (round(width, 3), 0.0),
        (round(width, 3), round(height, 3)),
        (0.0, round(height, 3)),
    }
    return not expected.issubset(set(points))


def _presentation_size(archive: zipfile.ZipFile) -> tuple[int, int]:
    try:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
    except (KeyError, ET.ParseError):
        return 0, 0
    size = root.find(f"{{{P_NS}}}sldSz")
    if size is None:
        return 0, 0
    return _int(size.get("cx")), _int(size.get("cy"))


def _shape_name(shape: ET.Element) -> str:
    node = shape.find(f"./{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
    return str(node.get("name") or "").strip() if node is not None else ""


def _shape_text(shape: ET.Element) -> str:
    return "".join(node.text or "" for node in shape.findall(f".//{{{A_NS}}}t")).strip()


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()


def _rect_percent(node: ET.Element) -> dict[str, float]:
    values: dict[str, float] = {}
    for key in ("l", "t", "r", "b"):
        try:
            values[key] = float(node.get(key, 0) or 0) / 100000.0
        except (TypeError, ValueError):
            values[key] = 0.0
    return values


def _slide_number(path: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", path)
    return int(match.group(1)) if match else 0


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coverage(imported: int, source: int) -> float:
    if source <= 0:
        return 1.0
    return min(1.0, max(0.0, float(imported) / float(source)))


if __name__ == "__main__":
    raise SystemExit(main())