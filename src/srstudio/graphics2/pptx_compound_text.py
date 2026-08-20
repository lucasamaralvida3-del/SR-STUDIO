from __future__ import annotations

"""Recupera texto de shapes PPTX que também usam picture fill.

Um ``p:sp`` pode declarar simultaneamente ``a:blip`` e ``p:txBody``. O pipeline
legado precisa escolher um único tipo e prioriza a imagem, portanto o texto desse
mesmo objeto não chega como node TEXT à SR Scene 2. Esta passagem materializa um
irmão textual imediatamente acima da imagem, preservando a geometria final já
corrigida pelos passes de imagem.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import math
import zipfile

from srstudio.importers.pptx.package_order import ordered_slide_paths

from .model import GraphicsDocument, GraphicsNode, NodeKind, Transform

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
PX_PER_INCH = 96.0


@dataclass(slots=True, frozen=True)
class PptxCompoundTextIssue:
    code: str
    slide: int
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxCompoundTextReport:
    source_shapes: int = 0
    matched_images: int = 0
    recovered_text_nodes: int = 0
    existing_text_nodes: int = 0
    issues: list[PptxCompoundTextIssue] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        if self.source_shapes == 0:
            return 1.0
        return (self.recovered_text_nodes + self.existing_text_nodes) / self.source_shapes

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_shapes": self.source_shapes,
            "matched_images": self.matched_images,
            "recovered_text_nodes": self.recovered_text_nodes,
            "existing_text_nodes": self.existing_text_nodes,
            "coverage": self.coverage,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def recover_pptx_compound_text(
    source: str | Path,
    document: GraphicsDocument,
) -> PptxCompoundTextReport:
    path = Path(source)
    report = PptxCompoundTextReport()
    if path.suffix.lower() != ".pptx" or not path.is_file():
        document.metadata["pptx_compound_text_recovery"] = report.to_dict()
        return report

    try:
        with zipfile.ZipFile(path) as archive:
            slide_width, slide_height = _presentation_size(archive)
            for slide, slide_path in enumerate(ordered_slide_paths(archive), start=1):
                if slide > len(document.pages):
                    break
                root = ET.fromstring(archive.read(slide_path))
                page = document.pages[slide - 1]
                for shape in root.findall(f".//{{{P_NS}}}sp"):
                    if shape.find(f".//{{{A_NS}}}blip") is None:
                        continue
                    text_body = shape.find(f"./{{{P_NS}}}txBody")
                    if text_body is None:
                        continue
                    text = _text_content(text_body)
                    if not text and len(text_body.findall(f"./{{{A_NS}}}p")) <= 1:
                        continue
                    report.source_shapes += 1
                    shape_name = _shape_name(shape)
                    text_nodes = _candidates(page.nodes.values(), shape_name, NodeKind.TEXT)
                    if text_nodes:
                        report.existing_text_nodes += 1
                        continue
                    images = _candidates(page.nodes.values(), shape_name, NodeKind.IMAGE)
                    if len(images) != 1:
                        code = "PPTX_COMPOUND_TEXT_IMAGE_AMBIGUOUS" if images else "PPTX_COMPOUND_TEXT_IMAGE_MISSING"
                        report.issues.append(
                            PptxCompoundTextIssue(
                                code,
                                slide,
                                shape_name,
                                f"Shape com picture fill + texto possui {len(images)} imagem(ns) correspondente(s); overlay não foi adivinhado.",
                            )
                        )
                        continue
                    image = images[0]
                    report.matched_images += 1
                    overlay = _overlay_node(
                        image,
                        shape_name,
                        text,
                        text_body,
                        page.width / max(1.0, float(slide_width)),
                        page.height / max(1.0, float(slide_height)),
                    )
                    _insert_immediately_above(page, image, overlay)
                    report.recovered_text_nodes += 1
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        report.issues.append(PptxCompoundTextIssue("PPTX_COMPOUND_TEXT_READ_FAILED", 0, "", str(exc)))

    document.metadata["pptx_compound_text_recovery"] = report.to_dict()
    return report


def _overlay_node(
    image: GraphicsNode,
    shape_name: str,
    text: str,
    text_body: ET.Element,
    scale_x: float,
    scale_y: float,
) -> GraphicsNode:
    body = text_body.find(f"{{{A_NS}}}bodyPr")
    run = _first_run_properties(text_body)
    paragraph = text_body.find(f".//{{{A_NS}}}pPr")
    family = _font_family(run)
    font_size = _font_size(run)
    style: dict[str, Any] = {
        "font_family": family or "Arial",
        "source_font_family": family,
        "font_size": font_size if font_size > 0.0 else 12.0,
        "bold": _bool_attr(run, "b"),
        "italic": _bool_attr(run, "i"),
        "fill": _text_color(run) or "#162033",
        "align": _horizontal_alignment(paragraph),
        "v_align": _vertical_alignment(body),
    }
    if body is not None:
        style["text_insets"] = {
            "left": _emu_attr(body, "lIns") * scale_x,
            "top": _emu_attr(body, "tIns") * scale_y,
            "right": _emu_attr(body, "rIns") * scale_x,
            "bottom": _emu_attr(body, "bIns") * scale_y,
        }
        if body.find(f"{{{A_NS}}}spAutoFit") is not None:
            style["fit_inside_box"] = False
            style["pptx_auto_fit"] = "shape"
        elif body.find(f"{{{A_NS}}}normAutofit") is not None:
            style["fit_inside_box"] = True
            style["pptx_auto_fit"] = "normal"
        elif body.find(f"{{{A_NS}}}noAutofit") is not None:
            style["fit_inside_box"] = False
            style["pptx_auto_fit"] = "none"
    if run is not None and run.get("spc") not in (None, ""):
        try:
            letter_pt = float(run.get("spc") or 0.0) / 100.0
            style["letter_spacing_pt"] = letter_pt
            style["letter_spacing"] = letter_pt * PX_PER_INCH / 72.0
        except (TypeError, ValueError):
            pass
    if paragraph is not None:
        line = paragraph.find(f"{{{A_NS}}}lnSpc")
        if line is not None and len(line):
            child = list(line)[0]
            kind = child.tag.rsplit("}", 1)[-1]
            try:
                value = float(child.get("val") or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if kind == "spcPts":
                points = value / 100.0
                style["line_spacing_pt"] = points
                style["line_spacing_px"] = points * PX_PER_INCH / 72.0
            elif kind == "spcPct":
                style["line_spacing_percent"] = value / 1000.0

    transform = image.transform
    return GraphicsNode(
        kind=NodeKind.TEXT,
        name=shape_name or image.name,
        transform=Transform(
            x=float(transform.x),
            y=float(transform.y),
            width=float(transform.width),
            height=float(transform.height),
            rotation=float(transform.rotation),
            scale_x=float(transform.scale_x),
            scale_y=float(transform.scale_y),
            pivot_x=float(transform.pivot_x),
            pivot_y=float(transform.pivot_y),
        ),
        z_index=int(image.z_index) + 1,
        locked=bool(image.locked),
        visible=bool(image.visible),
        opacity=float(image.opacity),
        text=text,
        style=style,
        metadata={
            "source": "pptx-compound-text",
            "source_name": shape_name or image.name,
            "pptx_compound_text_recovered": True,
            "pptx_compound_owner_id": image.id,
            "pptx_shape_name": shape_name or image.name,
            "grouped": bool(image.metadata.get("grouped", False)),
            "group_depth": int(image.metadata.get("group_depth", 0) or 0),
            "group_name": str(image.metadata.get("group_name") or ""),
        },
    )


def _insert_immediately_above(page, image: GraphicsNode, overlay: GraphicsNode) -> None:
    base = int(image.z_index)
    for node in page.nodes.values():
        if node.id != image.id and int(node.z_index) > base:
            node.z_index = int(node.z_index) + 1
    overlay.z_index = base + 1
    page.add_node(overlay)


def _text_content(text_body: ET.Element) -> str:
    paragraphs: list[str] = []
    for paragraph in text_body.findall(f"./{{{A_NS}}}p"):
        parts: list[str] = []
        for child in list(paragraph):
            tag = child.tag.rsplit("}", 1)[-1]
            if tag in {"r", "fld"}:
                text = child.find(f"{{{A_NS}}}t")
                if text is not None and text.text is not None:
                    parts.append(text.text)
            elif tag == "br":
                parts.append("\n")
            elif tag == "tab":
                parts.append("\t")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs)


def _candidates(nodes, name: str, kind: NodeKind) -> list[GraphicsNode]:
    target = _normal(name)
    if not target:
        return []
    return [
        node
        for node in nodes
        if node.kind is kind and _normal((node.metadata or {}).get("source_name") or node.name) == target
    ]


def _shape_name(shape: ET.Element) -> str:
    node = shape.find(f"./{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
    return str(node.get("name") or "").strip() if node is not None else ""


def _first_run_properties(text_body: ET.Element) -> ET.Element | None:
    for path in (
        f".//{{{A_NS}}}rPr",
        f".//{{{A_NS}}}defRPr",
        f".//{{{A_NS}}}endParaRPr",
    ):
        node = text_body.find(path)
        if node is not None:
            return node
    return None


def _font_family(run: ET.Element | None) -> str:
    if run is None:
        return ""
    latin = run.find(f"{{{A_NS}}}latin")
    return str(latin.get("typeface") or "").strip() if latin is not None else ""


def _font_size(run: ET.Element | None) -> float:
    if run is None:
        return 0.0
    try:
        value = float(run.get("sz") or 0.0) / 100.0
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _text_color(run: ET.Element | None) -> str:
    if run is None:
        return ""
    solid = run.find(f"{{{A_NS}}}solidFill")
    if solid is None:
        return ""
    rgb = solid.find(f"{{{A_NS}}}srgbClr")
    if rgb is not None and rgb.get("val"):
        return f"#{str(rgb.get('val')).upper()}"
    return ""


def _horizontal_alignment(paragraph: ET.Element | None) -> str:
    value = str(paragraph.get("algn") or "").strip().casefold() if paragraph is not None else ""
    return {"l": "left", "ctr": "center", "r": "right"}.get(value, "left")


def _vertical_alignment(body: ET.Element | None) -> str:
    value = str(body.get("anchor") or "").strip().casefold() if body is not None else ""
    return {"t": "top", "ctr": "center", "b": "bottom"}.get(value, "top")


def _bool_attr(node: ET.Element | None, key: str) -> bool:
    if node is None:
        return False
    return str(node.get(key, "")).strip().lower() in {"1", "true", "yes", "on"}


def _emu_attr(node: ET.Element, key: str) -> float:
    try:
        value = float(node.get(key, 0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _presentation_size(archive: zipfile.ZipFile) -> tuple[float, float]:
    try:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
        node = root.find(f".//{{{P_NS}}}sldSz")
        if node is not None:
            width = float(node.get("cx") or 12192000.0)
            height = float(node.get("cy") or 6858000.0)
            if width > 0.0 and height > 0.0:
                return width, height
    except (KeyError, ET.ParseError, TypeError, ValueError):
        pass
    return 12192000.0, 6858000.0


def _normal(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())
