from __future__ import annotations

"""Preserva visual de shapes de texto e alpha sRGB na SR Scene 2.

O pipeline legado converte ``p:sp`` com texto em um único node TEXT. Quando o
mesmo shape possui fill/outline explícito, a superfície visual do shape desaparece.
Este passe materializa um companion visual atrás do texto para geometrias preset
que a Scene representa sem aproximação (rect/ellipse) e corrige cores sRGB com
``a:alpha`` para o formato Qt ``#AARRGGBB``.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import zipfile

from srstudio.importers.pptx.package_order import ordered_slide_paths

from .model import GraphicsDocument, GraphicsNode, NodeKind, Transform

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


@dataclass(slots=True, frozen=True)
class PptxShapeVisualIssue:
    code: str
    slide: int
    shape_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxShapeVisualReport:
    text_shapes: int = 0
    text_colors_corrected: int = 0
    compound_text_colors_corrected: int = 0
    visual_shapes: int = 0
    visuals_recovered: int = 0
    existing_visuals: int = 0
    pure_shape_colors_corrected: int = 0
    deferred_geometry: int = 0
    issues: list[PptxShapeVisualIssue] = field(default_factory=list)

    @property
    def visual_coverage(self) -> float:
        if self.visual_shapes == 0:
            return 1.0
        return (self.visuals_recovered + self.existing_visuals) / self.visual_shapes

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_shapes": self.text_shapes,
            "text_colors_corrected": self.text_colors_corrected,
            "compound_text_colors_corrected": self.compound_text_colors_corrected,
            "visual_shapes": self.visual_shapes,
            "visuals_recovered": self.visuals_recovered,
            "existing_visuals": self.existing_visuals,
            "pure_shape_colors_corrected": self.pure_shape_colors_corrected,
            "deferred_geometry": self.deferred_geometry,
            "visual_coverage": self.visual_coverage,
            "issues": [item.to_dict() for item in self.issues],
        }


def recover_pptx_shape_visuals(
    source: str | Path,
    document: GraphicsDocument,
) -> PptxShapeVisualReport:
    path = Path(source)
    report = PptxShapeVisualReport()
    if path.suffix.lower() != ".pptx" or not path.is_file():
        document.metadata["pptx_shape_visual_recovery"] = report.to_dict()
        return report

    try:
        with zipfile.ZipFile(path) as archive:
            slide_width, slide_height = _presentation_size(archive)
            for slide, slide_path in enumerate(ordered_slide_paths(archive), start=1):
                if slide > len(document.pages):
                    break
                root = ET.fromstring(archive.read(slide_path))
                page = document.pages[slide - 1]
                scale_x = page.width / max(1.0, slide_width)
                scale_y = page.height / max(1.0, slide_height)
                for shape in root.findall(f".//{{{P_NS}}}sp"):
                    name = _shape_name(shape)
                    if not name:
                        continue
                    text_body = shape.find(f"./{{{P_NS}}}txBody")
                    has_text = text_body is not None and _has_text_contract(text_body)
                    if shape.find(f".//{{{A_NS}}}blip") is not None:
                        # Picture-filled p:sp já possui um owner visual IMAGE.
                        # Aqui preservamos apenas o texto compound sobreposto,
                        # sem criar um segundo backplate concorrente.
                        if has_text and text_body is not None:
                            _recover_compound_text_color(page, text_body, name, slide, report)
                        continue
                    if has_text and text_body is not None:
                        _recover_text_shape(page, shape, text_body, name, slide, scale_x, scale_y, report)
                    else:
                        _recover_pure_shape_color(page, shape, name, scale_x, scale_y, report)
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        report.issues.append(PptxShapeVisualIssue("PPTX_SHAPE_VISUAL_READ_FAILED", 0, "", str(exc)))

    document.metadata["pptx_shape_visual_recovery"] = report.to_dict()
    return report


def _recover_compound_text_color(
    page,
    text_body: ET.Element,
    name: str,
    slide: int,
    report: PptxShapeVisualReport,
) -> None:
    target = _normal(name)
    candidates = [
        node
        for node in page.nodes.values()
        if node.kind is NodeKind.TEXT
        and bool(node.metadata.get("pptx_compound_text_recovered"))
        and _normal((node.metadata or {}).get("source_name") or node.name) == target
    ]
    if len(candidates) != 1:
        code = "PPTX_COMPOUND_TEXT_AMBIGUOUS" if candidates else "PPTX_COMPOUND_TEXT_MISSING"
        report.issues.append(
            PptxShapeVisualIssue(
                code,
                slide,
                name,
                f"Shape picture-fill possui {len(candidates)} overlay(s) TEXT compound correspondente(s).",
            )
        )
        return
    color = _text_color(text_body)
    if color and _set_text_color(candidates[0], color):
        report.compound_text_colors_corrected += 1


def _recover_text_shape(
    page,
    shape: ET.Element,
    text_body: ET.Element,
    name: str,
    slide: int,
    scale_x: float,
    scale_y: float,
    report: PptxShapeVisualReport,
) -> None:
    report.text_shapes += 1
    text_nodes = _candidates(page.nodes.values(), name, {NodeKind.TEXT}, exclude_companions=True)
    if len(text_nodes) != 1:
        code = "PPTX_TEXT_SHAPE_TEXT_AMBIGUOUS" if text_nodes else "PPTX_TEXT_SHAPE_TEXT_MISSING"
        report.issues.append(
            PptxShapeVisualIssue(code, slide, name, f"Shape de texto possui {len(text_nodes)} node(s) TEXT correspondente(s).")
        )
        return
    text_node = text_nodes[0]
    text_color = _text_color(text_body)
    if text_color and _set_text_color(text_node, text_color):
        report.text_colors_corrected += 1

    fill, outline, stroke_width = _shape_paint(shape, scale_x, scale_y)
    if not fill and not outline:
        return
    report.visual_shapes += 1

    companions = [
        node
        for node in page.nodes.values()
        if str(node.metadata.get("pptx_compound_owner_id") or "") == text_node.id
        and bool(node.metadata.get("pptx_text_shape_visual_recovered"))
    ]
    if len(companions) == 1:
        report.existing_visuals += 1
        return
    if len(companions) > 1:
        report.issues.append(
            PptxShapeVisualIssue(
                "PPTX_TEXT_SHAPE_VISUAL_AMBIGUOUS",
                slide,
                name,
                f"Shape de texto já possui {len(companions)} companions visuais.",
            )
        )
        return

    kind = _geometry_kind(shape)
    if kind is None:
        report.deferred_geometry += 1
        report.issues.append(
            PptxShapeVisualIssue(
                "PPTX_TEXT_SHAPE_GEOMETRY_DEFERRED",
                slide,
                name,
                "Fill/outline existe, mas a geometria do shape não é rect/ellipse representável sem aproximação.",
            )
        )
        return

    visual = _visual_node(text_node, name, kind, fill, outline, stroke_width)
    _insert_immediately_below(page, text_node, visual)
    report.visuals_recovered += 1


def _recover_pure_shape_color(
    page,
    shape: ET.Element,
    name: str,
    scale_x: float,
    scale_y: float,
    report: PptxShapeVisualReport,
) -> None:
    nodes = _candidates(
        page.nodes.values(),
        name,
        {NodeKind.RECT, NodeKind.ELLIPSE, NodeKind.LINE, NodeKind.PATH},
        exclude_companions=True,
    )
    if len(nodes) != 1:
        return
    fill, outline, stroke_width = _shape_paint(shape, scale_x, scale_y)
    node = nodes[0]
    changed = False
    if fill and node.style.get("fill") != fill:
        node.style["fill"] = fill
        changed = True
    if outline:
        if node.style.get("stroke") != outline:
            node.style["stroke"] = outline
            changed = True
        if node.style.get("outline") != outline:
            node.style["outline"] = outline
            changed = True
        if float(node.style.get("stroke_width", -1.0) or 0.0) != float(stroke_width):
            node.style["stroke_width"] = stroke_width
            changed = True
    if changed:
        report.pure_shape_colors_corrected += 1
        node.metadata["pptx_shape_alpha_recovered"] = True


def _visual_node(
    owner: GraphicsNode,
    name: str,
    kind: NodeKind,
    fill: str,
    outline: str,
    stroke_width: float,
) -> GraphicsNode:
    transform = owner.transform
    style: dict[str, Any] = {
        "fill": fill or "#00000000",
        "stroke": outline or "#00000000",
        "outline": outline or "#00000000",
        "stroke_width": stroke_width,
    }
    return GraphicsNode(
        kind=kind,
        name=name,
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
        z_index=int(owner.z_index),
        locked=bool(owner.locked),
        visible=bool(owner.visible),
        opacity=float(owner.opacity),
        style=style,
        metadata={
            "source": "pptx-text-shape-visual",
            "source_name": name,
            "pptx_text_shape_visual_recovered": True,
            "pptx_compound_owner_id": owner.id,
            "grouped": bool(owner.metadata.get("grouped", False)),
            "group_depth": int(owner.metadata.get("group_depth", 0) or 0),
            "group_name": str(owner.metadata.get("group_name") or ""),
        },
    )


def _insert_immediately_below(page, owner: GraphicsNode, visual: GraphicsNode) -> None:
    base = int(owner.z_index)
    for node in page.nodes.values():
        if node.id != owner.id and int(node.z_index) > base:
            node.z_index = int(node.z_index) + 1
    owner.z_index = base + 1
    visual.z_index = base
    page.add_node(visual)


def _shape_paint(shape: ET.Element, scale_x: float, scale_y: float) -> tuple[str, str, float]:
    sppr = shape.find(f"./{{{P_NS}}}spPr")
    if sppr is None:
        return "", "", 0.0
    fill = _solid_color(sppr.find(f"{{{A_NS}}}solidFill"))
    line = sppr.find(f"{{{A_NS}}}ln")
    outline = _solid_color(line.find(f"{{{A_NS}}}solidFill")) if line is not None else ""
    stroke_width = 0.0
    if line is not None and line.get("w") not in (None, ""):
        try:
            source_width = float(line.get("w") or 0.0)
            average_scale = (abs(scale_x) + abs(scale_y)) / 2.0
            stroke_width = source_width * average_scale
        except (TypeError, ValueError):
            stroke_width = 0.0
    return fill, outline, max(0.0, stroke_width)


def _text_color(text_body: ET.Element) -> str:
    for path in (
        f".//{{{A_NS}}}rPr/{{{A_NS}}}solidFill",
        f".//{{{A_NS}}}defRPr/{{{A_NS}}}solidFill",
        f".//{{{A_NS}}}endParaRPr/{{{A_NS}}}solidFill",
    ):
        color = _solid_color(text_body.find(path))
        if color:
            return color
    return ""


def _solid_color(solid_fill: ET.Element | None) -> str:
    if solid_fill is None:
        return ""
    rgb = solid_fill.find(f"{{{A_NS}}}srgbClr")
    if rgb is None or not rgb.get("val"):
        return ""
    value = str(rgb.get("val") or "").strip().upper()
    if len(value) != 6:
        return ""
    alpha = 100000.0
    alpha_node = rgb.find(f"{{{A_NS}}}alpha")
    if alpha_node is not None and alpha_node.get("val") not in (None, ""):
        try:
            alpha = max(0.0, min(100000.0, float(alpha_node.get("val") or 100000.0)))
        except (TypeError, ValueError):
            alpha = 100000.0
    if alpha >= 99999.5:
        return f"#{value}"
    alpha_byte = max(0, min(255, round(alpha * 255.0 / 100000.0)))
    return f"#{alpha_byte:02X}{value}"


def _set_text_color(node: GraphicsNode, color: str) -> bool:
    previous_color = node.style.get("color")
    previous_fill = node.style.get("fill")
    if previous_color == color and previous_fill == color:
        return False
    node.style["color"] = color
    node.style["fill"] = color
    node.metadata["pptx_text_alpha_recovered"] = True
    return True


def _geometry_kind(shape: ET.Element) -> NodeKind | None:
    sppr = shape.find(f"./{{{P_NS}}}spPr")
    if sppr is None:
        return None
    preset = sppr.find(f"{{{A_NS}}}prstGeom")
    if preset is None:
        return None
    name = str(preset.get("prst") or "").strip().casefold()
    # SR Scene 2 não possui corner-radius canônico hoje. Preservar roundRect
    # como RECT seria uma aproximação silenciosa, então shapes arredondados
    # permanecem explicitamente deferidos até existir geometria equivalente.
    if name == "rect":
        return NodeKind.RECT
    if name == "ellipse":
        return NodeKind.ELLIPSE
    return None


def _has_text_contract(text_body: ET.Element) -> bool:
    paragraphs = text_body.findall(f"./{{{A_NS}}}p")
    if len(paragraphs) > 1:
        return True
    return any((node.text or "") != "" for node in text_body.findall(f".//{{{A_NS}}}t"))


def _candidates(nodes, name: str, kinds: set[NodeKind], *, exclude_companions: bool) -> list[GraphicsNode]:
    target = _normal(name)
    if not target:
        return []
    return [
        node
        for node in nodes
        if node.kind in kinds
        and (not exclude_companions or not node.metadata.get("pptx_compound_owner_id"))
        and _normal((node.metadata or {}).get("source_name") or node.name) == target
    ]


def _shape_name(shape: ET.Element) -> str:
    node = shape.find(f"./{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
    return str(node.get("name") or "").strip() if node is not None else ""


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
