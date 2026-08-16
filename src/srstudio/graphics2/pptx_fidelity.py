from __future__ import annotations

"""Camada de fidelidade OOXML para importações Canva/PPTX do Graphics Engine 2.

O importador legado continua responsável pela semântica/Smart Slots. Este módulo
relê somente os detalhes visuais que não podem ser descartados sem alterar o
layout: fontes embutidas, auto-fit, espaçamento e caminhos ``custGeom``.
"""

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import posixpath
import re
import struct
import zipfile

from .model import GraphicsDocument, GraphicsNode, NodeKind

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
EMU_PER_INCH = 914400.0
PX_PER_INCH = 96.0


@dataclass(slots=True)
class EmbeddedPptxFont:
    family: str
    style: str
    relationship_id: str
    internal_path: str
    extracted_path: str = ""
    sfnt_format: str = ""
    sha256: str = ""
    fs_type: int = 0
    runtime_allowed: bool = True
    source_size: int = 0
    font_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PptxFidelityReport:
    fonts_declared: int = 0
    fonts_extracted: int = 0
    text_nodes_enriched: int = 0
    custom_paths_enriched: int = 0
    image_clips_enriched: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def enhance_pptx_document(
    source: str | Path,
    document: GraphicsDocument,
    *,
    cache_dir: str | Path | None = None,
) -> PptxFidelityReport:
    """Enriquece um SR Scene importado com informação visual nativa do PPTX.

    A função nunca altera geometria x/y/w/h já validada pelo pipeline. Ela só
    adiciona metadados/estilo necessários para o renderer reproduzir o arquivo
    original com maior fidelidade.
    """

    path = Path(source)
    report = PptxFidelityReport()
    if path.suffix.lower() != ".pptx" or not path.is_file():
        return report

    if cache_dir is None:
        digest = sha256(f"{path.resolve()}:{path.stat().st_mtime_ns}".encode()).hexdigest()[:16]
        cache_root = Path.home() / ".srstudio5" / "imports-g2" / digest
    else:
        cache_root = Path(cache_dir)
    font_dir = cache_root / "fonts"

    try:
        with zipfile.ZipFile(path) as archive:
            slide_width, slide_height = _presentation_size(archive)
            fonts = _extract_embedded_fonts(archive, font_dir, report)
            _apply_embedded_fonts(document, fonts, report)
            slides = sorted(
                (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=_slide_number,
            )
            for page_index, slide_path in enumerate(slides):
                if page_index >= len(document.pages):
                    break
                try:
                    root = ET.fromstring(archive.read(slide_path))
                except (KeyError, ET.ParseError) as exc:
                    report.warnings.append(f"{slide_path}: XML inválido ({exc}).")
                    continue
                _enrich_page(
                    document.pages[page_index],
                    root,
                    slide_width,
                    slide_height,
                    report,
                )
    except (OSError, zipfile.BadZipFile) as exc:
        report.warnings.append(f"Não foi possível abrir o PPTX para fidelidade avançada: {exc}")

    document.metadata["pptx_fidelity"] = report.to_dict()
    return report


def _extract_embedded_fonts(
    archive: zipfile.ZipFile,
    font_dir: Path,
    report: PptxFidelityReport,
) -> list[EmbeddedPptxFont]:
    try:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
    except (KeyError, ET.ParseError):
        return []
    relationships = _presentation_relationships(archive)
    fonts: list[EmbeddedPptxFont] = []
    for entry in presentation.findall(f".//{{{P_NS}}}embeddedFont"):
        descriptor = entry.find(f"{{{P_NS}}}font")
        family = str(descriptor.get("typeface") or "").strip() if descriptor is not None else ""
        if not family:
            continue
        for variant in ("regular", "bold", "italic", "boldItalic"):
            node = entry.find(f"{{{P_NS}}}{variant}")
            if node is None:
                continue
            rid = str(node.get(f"{{{R_NS}}}id") or "")
            internal = relationships.get(rid, "")
            report.fonts_declared += 1
            item = EmbeddedPptxFont(family, variant, rid, internal)
            if not internal or internal not in archive.namelist():
                report.warnings.append(f"Fonte embutida '{family}' sem payload resolvido ({rid}).")
                fonts.append(item)
                continue
            raw = archive.read(internal)
            item.source_size = len(raw)
            payload, sfnt_format = _sfnt_payload(raw)
            if payload is None:
                report.warnings.append(f"Fonte embutida '{family}' usa formato não reconhecido.")
                fonts.append(item)
                continue
            item.font_size = len(payload)
            item.sfnt_format = sfnt_format
            item.sha256 = sha256(payload).hexdigest()
            item.fs_type = _sfnt_fs_type(payload)
            item.runtime_allowed = not bool(item.fs_type & 0x0002)
            if not item.runtime_allowed:
                report.warnings.append(
                    f"Fonte '{family}' possui flag de embedding restrito (fsType={item.fs_type}); "
                    "não será registrada automaticamente."
                )
                fonts.append(item)
                continue
            extension = ".otf" if sfnt_format == "otf" else ".ttc" if sfnt_format == "ttc" else ".ttf"
            safe_family = _safe_filename(family)
            safe_style = _safe_filename(variant)
            target = font_dir / f"{safe_family}-{safe_style}-{item.sha256[:12]}{extension}"
            try:
                font_dir.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.stat().st_size != len(payload):
                    target.write_bytes(payload)
                item.extracted_path = str(target)
                report.fonts_extracted += 1
            except OSError as exc:
                report.warnings.append(f"Falha ao extrair fonte '{family}': {exc}")
            fonts.append(item)
    return fonts


def _apply_embedded_fonts(
    document: GraphicsDocument,
    fonts: list[EmbeddedPptxFont],
    report: PptxFidelityReport,
) -> None:
    entries = [font.to_dict() for font in fonts]
    document.metadata["embedded_fonts"] = entries
    exact: dict[str, EmbeddedPptxFont] = {}
    for font in fonts:
        if font.extracted_path and font.runtime_allowed:
            exact.setdefault(font.family.casefold(), font)
    if not exact:
        return
    for page in document.pages:
        for node in page.nodes.values():
            if node.kind is not NodeKind.TEXT:
                continue
            source_family = str(
                node.style.get("source_font_family")
                or node.metadata.get("source_font_name")
                or node.style.get("font_family")
                or ""
            ).strip()
            embedded = exact.get(source_family.casefold())
            if embedded is None:
                continue
            node.style["font_family"] = embedded.family
            node.style["source_font_family"] = embedded.family
            node.metadata["embedded_font_path"] = embedded.extracted_path
            node.metadata["embedded_font_sha256"] = embedded.sha256
            report.text_nodes_enriched += 1


def _enrich_page(page, root: ET.Element, slide_width: int, slide_height: int, report: PptxFidelityReport) -> None:
    by_name: dict[str, GraphicsNode] = {}
    for node in page.nodes.values():
        source_name = str(node.metadata.get("source_name") or node.name or "").strip()
        if source_name:
            by_name.setdefault(source_name, node)

    scale_x = page.width / max(1.0, float(slide_width))
    scale_y = page.height / max(1.0, float(slide_height))
    for shape in root.findall(f".//{{{P_NS}}}sp"):
        name_node = shape.find(f".//{{{P_NS}}}cNvPr")
        name = str(name_node.get("name") or "").strip() if name_node is not None else ""
        node = by_name.get(name)
        if node is None:
            continue

        text_body = shape.find(f"{{{P_NS}}}txBody")
        if text_body is not None and node.kind is NodeKind.TEXT:
            _enrich_text(node, text_body, scale_x, scale_y)

        path_spec = _custom_path_spec(shape)
        if path_spec is None:
            continue
        if node.kind is NodeKind.IMAGE:
            if not _path_is_axis_aligned_rect(path_spec):
                node.metadata["clip_path"] = path_spec
                report.image_clips_enriched += 1
        elif node.kind in {NodeKind.RECT, NodeKind.PATH}:
            # Retângulos customizados simples não precisam de uma máscara extra.
            # Formas curvas/irregulares preservam o caminho DrawingML exato.
            if not _path_is_axis_aligned_rect(path_spec):
                node.metadata["custom_path"] = path_spec
                report.custom_paths_enriched += 1


def _enrich_text(node: GraphicsNode, text_body: ET.Element, scale_x: float, scale_y: float) -> None:
    body = text_body.find(f"{{{A_NS}}}bodyPr")
    if body is not None:
        insets = {
            "left": _emu_attr(body, "lIns") * scale_x,
            "top": _emu_attr(body, "tIns") * scale_y,
            "right": _emu_attr(body, "rIns") * scale_x,
            "bottom": _emu_attr(body, "bIns") * scale_y,
        }
        if any(abs(value) > 1e-9 for value in insets.values()):
            node.style["text_insets"] = insets
        if body.find(f"{{{A_NS}}}spAutoFit") is not None:
            node.style["fit_inside_box"] = True
            node.style["pptx_auto_fit"] = "shape"
        elif body.find(f"{{{A_NS}}}normAutofit") is not None:
            node.style["fit_inside_box"] = True
            node.style["pptx_auto_fit"] = "normal"
        elif body.find(f"{{{A_NS}}}noAutofit") is not None:
            node.style["pptx_auto_fit"] = "none"

    run_properties = text_body.find(f".//{{{A_NS}}}rPr")
    if run_properties is None:
        run_properties = text_body.find(f".//{{{A_NS}}}defRPr")
    if run_properties is not None and run_properties.get("spc") not in (None, ""):
        try:
            # DrawingML armazena espaçamento entre caracteres em centésimos de ponto.
            letter_pt = float(run_properties.get("spc") or 0) / 100.0
            node.style["letter_spacing"] = letter_pt * PX_PER_INCH / 72.0
            node.style["letter_spacing_pt"] = letter_pt
        except (TypeError, ValueError):
            pass

    paragraph = text_body.find(f".//{{{A_NS}}}pPr")
    if paragraph is not None:
        line_spacing = paragraph.find(f"{{{A_NS}}}lnSpc")
        if line_spacing is not None and len(line_spacing):
            child = list(line_spacing)[0]
            kind = child.tag.rsplit("}", 1)[-1]
            value = child.get("val")
            try:
                numeric = float(value or 0)
            except (TypeError, ValueError):
                numeric = 0.0
            if kind == "spcPts":
                points = numeric / 100.0
                node.style["line_spacing_px"] = points * PX_PER_INCH / 72.0
                node.style["line_spacing_pt"] = points
            elif kind == "spcPct":
                node.style["line_spacing_percent"] = numeric / 1000.0


def _custom_path_spec(shape: ET.Element) -> dict[str, Any] | None:
    sppr = shape.find(f"{{{P_NS}}}spPr")
    if sppr is None:
        return None
    custom = sppr.find(f"{{{A_NS}}}custGeom")
    if custom is None:
        return None
    path_list = custom.find(f"{{{A_NS}}}pathLst")
    if path_list is None:
        return None
    paths: list[dict[str, Any]] = []
    max_width = 0.0
    max_height = 0.0
    for path in path_list.findall(f"{{{A_NS}}}path"):
        width = _number(path.get("w"))
        height = _number(path.get("h"))
        max_width = max(max_width, width)
        max_height = max(max_height, height)
        commands = _path_commands(path)
        if commands:
            paths.append(
                {
                    "width": width,
                    "height": height,
                    "fill_mode": str(path.get("fill") or "norm"),
                    "stroke": str(path.get("stroke") or "1") not in {"0", "false", "False"},
                    "commands": commands,
                }
            )
    if not paths:
        return None
    return {"width": max_width, "height": max_height, "paths": paths}


def _path_commands(path: ET.Element) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for child in list(path):
        tag = child.tag.rsplit("}", 1)[-1]
        points = [
            [_number(point.get("x")), _number(point.get("y"))]
            for point in child.findall(f".//{{{A_NS}}}pt")
        ]
        if tag == "moveTo" and points:
            commands.append({"op": "M", "points": points[:1]})
        elif tag == "lnTo" and points:
            commands.append({"op": "L", "points": points[:1]})
        elif tag == "cubicBezTo" and len(points) >= 3:
            commands.append({"op": "C", "points": points[:3]})
        elif tag == "quadBezTo" and len(points) >= 2:
            commands.append({"op": "Q", "points": points[:2]})
        elif tag == "arcTo":
            commands.append(
                {
                    "op": "A",
                    "wR": _number(child.get("wR")),
                    "hR": _number(child.get("hR")),
                    "stAng": _number(child.get("stAng")),
                    "swAng": _number(child.get("swAng")),
                }
            )
        elif tag == "close":
            commands.append({"op": "Z"})
    return commands


def _path_is_axis_aligned_rect(spec: dict[str, Any]) -> bool:
    paths = list(spec.get("paths") or [])
    if len(paths) != 1:
        return False
    path = paths[0]
    width = float(path.get("width") or spec.get("width") or 0)
    height = float(path.get("height") or spec.get("height") or 0)
    commands = list(path.get("commands") or [])
    points: list[tuple[float, float]] = []
    for command in commands:
        if command.get("op") in {"M", "L"} and command.get("points"):
            x, y = command["points"][0]
            points.append((round(float(x), 3), round(float(y), 3)))
        elif command.get("op") == "Z":
            continue
        else:
            return False
    if len(points) not in {4, 5} or width <= 0 or height <= 0:
        return False
    expected = {
        (0.0, 0.0),
        (round(width, 3), 0.0),
        (round(width, 3), round(height, 3)),
        (0.0, round(height, 3)),
    }
    return expected.issubset(set(points))


def _presentation_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    path = "ppt/_rels/presentation.xml.rels"
    try:
        root = ET.fromstring(archive.read(path))
    except (KeyError, ET.ParseError):
        return {}
    mapping: dict[str, str] = {}
    for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        rid = str(rel.get("Id") or "")
        target = str(rel.get("Target") or "")
        if rid and target:
            mapping[rid] = posixpath.normpath(posixpath.join("ppt", target))
    return mapping


def _sfnt_payload(raw: bytes) -> tuple[bytes | None, str]:
    direct = _sfnt_format(raw[:4])
    if direct:
        return raw, direct
    if len(raw) < 8:
        return None, ""
    try:
        eot_size, font_size = struct.unpack_from("<II", raw, 0)
    except struct.error:
        return None, ""
    offsets = []
    if eot_size >= font_size > 0:
        offsets.append(eot_size - font_size)
    if len(raw) >= font_size > 0:
        offsets.append(len(raw) - font_size)
    for offset in dict.fromkeys(offsets):
        if offset < 0 or offset + font_size > len(raw):
            continue
        payload = raw[offset : offset + font_size]
        fmt = _sfnt_format(payload[:4])
        if fmt:
            return payload, fmt
    return None, ""


def _sfnt_format(signature: bytes) -> str:
    if signature == b"OTTO":
        return "otf"
    if signature in {b"\x00\x01\x00\x00", b"true", b"typ1"}:
        return "ttf"
    if signature == b"ttcf":
        return "ttc"
    return ""


def _sfnt_fs_type(payload: bytes) -> int:
    if len(payload) < 12 or payload[:4] == b"ttcf":
        return 0
    try:
        num_tables = struct.unpack_from(">H", payload, 4)[0]
    except struct.error:
        return 0
    table_offset = 12
    for index in range(num_tables):
        record = table_offset + index * 16
        if record + 16 > len(payload):
            break
        tag = payload[record : record + 4]
        if tag != b"OS/2":
            continue
        try:
            offset = struct.unpack_from(">I", payload, record + 8)[0]
            if offset + 10 <= len(payload):
                return int(struct.unpack_from(">H", payload, offset + 8)[0])
        except struct.error:
            return 0
    return 0


def _presentation_size(archive: zipfile.ZipFile) -> tuple[int, int]:
    try:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
        node = root.find(f".//{{{P_NS}}}sldSz")
        if node is not None:
            return int(node.get("cx", 12192000)), int(node.get("cy", 6858000))
    except (KeyError, ET.ParseError, TypeError, ValueError):
        pass
    return 12192000, 6858000


def _slide_number(path: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", path)
    return int(match.group(1)) if match else 0


def _emu_attr(node: ET.Element, key: str) -> float:
    try:
        return float(node.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(value).strip())
    return cleaned.strip("-") or "font"
