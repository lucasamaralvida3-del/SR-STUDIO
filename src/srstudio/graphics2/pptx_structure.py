from __future__ import annotations

"""Auditoria estrutural OOXML para importações PPTX/Canva.

O Graphics Engine 2 não pode considerar um PPTX fiel apenas porque o número de
slides bate. O Canva frequentemente grava imagens como ``p:sp`` + ``a:blipFill``
(em vez de ``p:pic``), além de usar grupos, ``custGeom`` e ``stretch/fillRect``
em grande escala. Este módulo mede a estrutura fonte antes da conversão e
compara o que chegou ao SR Scene sem modificar geometria ou conteúdo.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import json
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxMappingAudit:
    source_slides: int = 0
    imported_pages: int = 0
    source_text_shapes: int = 0
    imported_text_nodes: int = 0
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
    def ready(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def audit_document(self, document: GraphicsDocument) -> PptxMappingAudit:
        imported_text = sum(
            1
            for page in document.pages
            for node in page.nodes.values()
            if node.kind is NodeKind.TEXT and str(node.text or "").strip()
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
        audit = PptxMappingAudit(
            source_slides=self.slide_count,
            imported_pages=len(document.pages),
            source_text_shapes=self.text_shapes,
            imported_text_nodes=imported_text,
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
        if self.image_custom_geometry and audit.image_clip_coverage < 0.90:
            audit.warnings.append(
                f"Cobertura de máscaras custGeom em imagens baixa: {audit.image_clip_coverage * 100:.2f}% "
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
        f"imagens={report.pictures + report.image_fill_shapes} "
        f"(pic={report.pictures}, blipFill={report.image_fill_shapes}) · "
        f"fillRect={report.image_fill_rects} (outset={report.image_fill_outsets}) · "
        f"máscaras={report.image_custom_geometry} · grupos={report.groups} · "
        f"custGeom={report.custom_geometry} · preços~={report.estimated_split_prices}"
    )
    print(f"SHA-256: {report.source_sha256 or '-'}")
    if args.slides:
        for slide in report.slides:
            print(
                f"  slide {slide.slide}: shapes={slide.shapes} textos={slide.text_shapes} "
                f"imagens={slide.pictures + slide.image_fill_shapes} grupos={slide.groups} "
                f"custGeom={slide.custom_geometry} fillRect={slide.image_fill_rects} "
                f"outset={slide.image_fill_outsets} máscaras={slide.image_custom_geometry} "
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
            cleaned = _clean_text(text)
            currencies += int(bool(_CURRENCY_RE.fullmatch(cleaned)))
            integers += int(bool(_INTEGER_RE.fullmatch(cleaned)))
            cents += int(bool(_CENTS_RE.fullmatch(cleaned)))
            units += int(bool(_UNIT_RE.fullmatch(cleaned)))

        has_image_fill = shape.find(f".//{{{A_NS}}}blip") is not None
        has_custom_geometry = shape.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}custGeom") is not None
        if has_image_fill:
            item.image_fill_shapes += 1
            if name:
                item.image_fill_shape_names.append(name)
            fill_rect = shape.find(f".//{{{A_NS}}}stretch/{{{A_NS}}}fillRect")
            if fill_rect is not None:
                item.image_fill_rects += 1
                if any(value < 0.0 for value in _rect_percent(fill_rect).values()):
                    item.image_fill_outsets += 1
            if has_custom_geometry:
                item.image_custom_geometry += 1
        if has_custom_geometry:
            item.custom_geometry += 1

    item.pictures = len(root.findall(f".//{{{P_NS}}}pic"))
    # p:pic também pode possuir stretch/fillRect. Contar aqui evita que o gate
    # trate somente o formato p:sp usado pelo Canva como relevante.
    for picture in root.findall(f".//{{{P_NS}}}pic"):
        fill_rect = picture.find(f".//{{{A_NS}}}stretch/{{{A_NS}}}fillRect")
        if fill_rect is not None:
            item.image_fill_rects += 1
            if any(value < 0.0 for value in _rect_percent(fill_rect).values()):
                item.image_fill_outsets += 1
        if picture.find(f"./{{{P_NS}}}spPr/{{{A_NS}}}custGeom") is not None:
            item.image_custom_geometry += 1

    item.groups = len(root.findall(f".//{{{P_NS}}}grpSp"))
    item.currency_tokens = currencies
    item.integer_tokens = integers
    item.cents_tokens = cents
    item.unit_tokens = units
    item.estimated_split_prices = min(currencies, integers, cents, units)
    return item


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
