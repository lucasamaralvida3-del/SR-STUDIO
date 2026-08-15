from __future__ import annotations

import hashlib
import math
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from srstudio.assets.font_fallbacks import preferred_windows_display_family


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True, slots=True)
class _Affine:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    def point(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.c * y + self.e, self.b * x + self.d * y + self.f

    def then(self, outer: "_Affine") -> "_Affine":
        """Return outer(self(point))."""
        return _Affine(
            a=outer.a * self.a + outer.c * self.b,
            b=outer.b * self.a + outer.d * self.b,
            c=outer.a * self.c + outer.c * self.d,
            d=outer.b * self.c + outer.d * self.d,
            e=outer.a * self.e + outer.c * self.f + outer.e,
            f=outer.b * self.e + outer.d * self.f + outer.f,
        )


@dataclass(slots=True)
class PptxElement:
    kind: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    text: str = ""
    media_path: str = ""
    name: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class PptxSlide:
    index: int
    width: int = 12192000
    height: int = 6858000
    elements: list[PptxElement] = field(default_factory=list)
    background: str = "#FFFFFF"


@dataclass(slots=True)
class PptxImportResult:
    slides: list[PptxSlide] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PptxImporter:
    """Canva-aware PPTX reader preserving fills, groups, typography and z-order."""

    def import_file(self, path: str | Path, media_dir: str | Path | None = None) -> PptxImportResult:
        source = Path(path)
        result = PptxImportResult()
        target_media = Path(media_dir) if media_dir else None
        if target_media:
            target_media.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as zf:
            slide_width, slide_height = self._presentation_size(zf)
            media_map = self._extract_media(zf, target_media) if target_media else {}
            slides = sorted(
                (name for name in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=self._slide_number,
            )
            for idx, slide_path in enumerate(slides, start=1):
                try:
                    result.slides.append(
                        self._read_slide(zf, slide_path, idx, slide_width, slide_height, media_map)
                    )
                except Exception as exc:
                    result.warnings.append(f"Slide {idx}: {exc}")
        return result

    def _read_slide(
        self,
        zf: zipfile.ZipFile,
        slide_path: str,
        index: int,
        slide_width: int,
        slide_height: int,
        media_map: dict[str, str],
    ) -> PptxSlide:
        root = ET.fromstring(zf.read(slide_path))
        rels = self._relationships(zf, slide_path)
        slide = PptxSlide(
            index=index,
            width=slide_width,
            height=slide_height,
            background=self._slide_background(root),
        )
        sp_tree = root.find(f".//{{{P_NS}}}spTree")
        if sp_tree is None:
            return slide
        identity = _Affine()
        for child in list(sp_tree):
            tag = child.tag.rsplit("}", 1)[-1]
            if tag in {"nvGrpSpPr", "grpSpPr"}:
                continue
            if tag == "sp":
                slide.elements.append(self._shape(child, rels, media_map, identity, len(slide.elements)))
            elif tag == "pic":
                slide.elements.append(self._picture(child, rels, media_map, identity, len(slide.elements)))
            elif tag == "graphicFrame":
                slide.elements.append(self._graphic(child, identity, len(slide.elements)))
            elif tag == "grpSp":
                slide.elements.extend(
                    self._group(child, rels, media_map, identity, len(slide.elements), depth=1)
                )
        return slide

    def _shape(
        self,
        node: ET.Element,
        rels: dict[str, str],
        media_map: dict[str, str],
        transform: _Affine,
        z_index: int,
    ) -> PptxElement:
        x, y, w, h = self._geometry(node, transform)
        text = self._text(node)
        media_path, media_meta = self._media(node, rels, media_map)
        metadata = self._common_metadata(node, z_index)
        metadata.update(self._shape_style(node))
        metadata.update(media_meta)
        if media_path:
            metadata["picture_fill"] = True
            kind = "image"
        elif text:
            kind = "text"
        else:
            kind = "shape"
        return PptxElement(kind, x, y, w, h, text, media_path, self._name(node), metadata)

    def _picture(
        self,
        node: ET.Element,
        rels: dict[str, str],
        media_map: dict[str, str],
        transform: _Affine,
        z_index: int,
    ) -> PptxElement:
        x, y, w, h = self._geometry(node, transform)
        media_path, media_meta = self._media(node, rels, media_map)
        metadata = self._common_metadata(node, z_index)
        metadata.update(media_meta)
        metadata["picture_fill"] = False
        return PptxElement("image", x, y, w, h, media_path=media_path, name=self._name(node), metadata=metadata)

    def _graphic(self, node: ET.Element, transform: _Affine, z_index: int) -> PptxElement:
        x, y, w, h = self._geometry(node, transform)
        return PptxElement(
            "graphic",
            x,
            y,
            w,
            h,
            name=self._name(node),
            metadata=self._common_metadata(node, z_index),
        )

    def _group(
        self,
        node: ET.Element,
        rels: dict[str, str],
        media_map: dict[str, str],
        parent: _Affine,
        z_start: int,
        depth: int,
    ) -> list[PptxElement]:
        matrix, rotation = self._group_transform(node)
        transform = matrix.then(parent)
        items: list[PptxElement] = []
        group_name = self._name(node)
        for child in list(node):
            tag = child.tag.rsplit("}", 1)[-1]
            if tag in {"nvGrpSpPr", "grpSpPr"}:
                continue
            z_index = z_start + len(items)
            if tag == "sp":
                item = self._shape(child, rels, media_map, transform, z_index)
                item.metadata.update(
                    {"grouped": True, "group_depth": depth, "group_name": group_name, "group_rotation": rotation}
                )
                items.append(item)
            elif tag == "pic":
                item = self._picture(child, rels, media_map, transform, z_index)
                item.metadata.update(
                    {"grouped": True, "group_depth": depth, "group_name": group_name, "group_rotation": rotation}
                )
                items.append(item)
            elif tag == "graphicFrame":
                item = self._graphic(child, transform, z_index)
                item.metadata.update(
                    {"grouped": True, "group_depth": depth, "group_name": group_name, "group_rotation": rotation}
                )
                items.append(item)
            elif tag == "grpSp":
                nested = self._group(
                    child,
                    rels,
                    media_map,
                    transform,
                    z_start + len(items),
                    depth=depth + 1,
                )
                items.extend(nested)
        return items

    def _relationships(self, zf: zipfile.ZipFile, slide_path: str) -> dict[str, str]:
        directory, filename = posixpath.split(slide_path)
        rel_path = posixpath.join(directory, "_rels", filename + ".rels")
        if rel_path not in zf.namelist():
            return {}
        root = ET.fromstring(zf.read(rel_path))
        rels: dict[str, str] = {}
        for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            target = rel.get("Target", "")
            rels[rel.get("Id", "")] = posixpath.normpath(posixpath.join(directory, target))
        return rels

    @staticmethod
    def _presentation_size(zf: zipfile.ZipFile) -> tuple[int, int]:
        try:
            root = ET.fromstring(zf.read("ppt/presentation.xml"))
            node = root.find(f".//{{{P_NS}}}sldSz")
            if node is not None:
                return int(node.get("cx", 12192000)), int(node.get("cy", 6858000))
        except (KeyError, ET.ParseError, ValueError):
            pass
        return 12192000, 6858000

    @staticmethod
    def _extract_media(zf: zipfile.ZipFile, target: Path | None) -> dict[str, str]:
        mapping: dict[str, str] = {}
        if target is None:
            return mapping
        for internal in zf.namelist():
            if not internal.startswith("ppt/media/") or internal.endswith("/"):
                continue
            data = zf.read(internal)
            digest = hashlib.sha256(data).hexdigest()[:20]
            suffix = Path(internal).suffix.lower() or ".bin"
            destination = target / f"{digest}{suffix}"
            if not destination.exists():
                destination.write_bytes(data)
            mapping[internal] = str(destination)
        return mapping

    def _media(
        self,
        node: ET.Element,
        rels: dict[str, str],
        media_map: dict[str, str],
    ) -> tuple[str, dict]:
        blip = node.find(f".//{{{A_NS}}}blip")
        if blip is None:
            return "", {}
        rid = blip.get(f"{{{R_NS}}}embed", "")
        internal = rels.get(rid, "")
        crop = node.find(f".//{{{A_NS}}}srcRect")
        fill_rect = node.find(f".//{{{A_NS}}}fillRect")
        alpha = blip.find(f".//{{{A_NS}}}alphaModFix")
        metadata = {
            "relationship_id": rid,
            "internal_media": internal,
            "crop": self._rect_percent(crop),
            "fill_rect": self._rect_percent(fill_rect),
            "opacity": self._alpha(alpha),
        }
        return media_map.get(internal, internal), metadata

    def _shape_style(self, node: ET.Element) -> dict:
        font_node = self._first_font_node(node)
        latin = font_node.find(f"{{{A_NS}}}latin") if font_node is not None else None
        paragraph = node.find(f".//{{{A_NS}}}pPr")
        body = node.find(f".//{{{A_NS}}}bodyPr")
        source_font = latin.get("typeface", "") if latin is not None else ""
        return {
            "fill": self._color(node.find(f".//{{{P_NS}}}spPr/{{{A_NS}}}solidFill")),
            "outline": self._color(node.find(f".//{{{P_NS}}}spPr/{{{A_NS}}}ln/{{{A_NS}}}solidFill")),
            "text_fill": self._text_color(node),
            "font_name": source_font,
            "display_font_name": preferred_windows_display_family(source_font),
            "source_font_name": source_font,
            "font_size_pt": self._font_size(font_node),
            "bold": self._bool_attr(font_node, "b"),
            "italic": self._bool_attr(font_node, "i"),
            "align": paragraph.get("algn", "") if paragraph is not None else "",
            "vertical_anchor": body.get("anchor", "") if body is not None else "",
            "body_wrap": body.get("wrap", "") if body is not None else "",
        }

    def _common_metadata(self, node: ET.Element, z_index: int) -> dict:
        xfrm = node.find(f".//{{{A_NS}}}xfrm")
        rotation = self._rotation(xfrm)
        return {
            "z_index": z_index,
            "rotation": rotation,
            "flip_h": self._bool_attr(xfrm, "flipH"),
            "flip_v": self._bool_attr(xfrm, "flipV"),
        }

    @staticmethod
    def _text(node: ET.Element) -> str:
        paragraphs: list[str] = []
        for paragraph in node.findall(f".//{{{A_NS}}}p"):
            text = "".join(t.text or "" for t in paragraph.findall(f".//{{{A_NS}}}t"))
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs).strip()

    @staticmethod
    def _geometry(node: ET.Element, transform: _Affine | None = None) -> tuple[int, int, int, int]:
        xfrm = node.find(f".//{{{A_NS}}}xfrm")
        if xfrm is None:
            return 0, 0, 0, 0
        off = xfrm.find(f"{{{A_NS}}}off")
        ext = xfrm.find(f"{{{A_NS}}}ext")
        x = int(off.get("x", 0)) if off is not None else 0
        y = int(off.get("y", 0)) if off is not None else 0
        w = int(ext.get("cx", 0)) if ext is not None else 0
        h = int(ext.get("cy", 0)) if ext is not None else 0
        if transform is None:
            return x, y, w, h
        corners = [
            transform.point(x, y),
            transform.point(x + w, y),
            transform.point(x, y + h),
            transform.point(x + w, y + h),
        ]
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        left, top = min(xs), min(ys)
        right, bottom = max(xs), max(ys)
        return round(left), round(top), max(0, round(right - left)), max(0, round(bottom - top))

    @classmethod
    def _group_transform(cls, node: ET.Element) -> tuple[_Affine, float]:
        xfrm = node.find(f"./{{{P_NS}}}grpSpPr/{{{A_NS}}}xfrm")
        if xfrm is None:
            return _Affine(), 0.0
        off = xfrm.find(f"{{{A_NS}}}off")
        ext = xfrm.find(f"{{{A_NS}}}ext")
        ch_off = xfrm.find(f"{{{A_NS}}}chOff")
        ch_ext = xfrm.find(f"{{{A_NS}}}chExt")
        ox = float(off.get("x", 0)) if off is not None else 0.0
        oy = float(off.get("y", 0)) if off is not None else 0.0
        ew = float(ext.get("cx", 1)) if ext is not None else 1.0
        eh = float(ext.get("cy", 1)) if ext is not None else 1.0
        cx = float(ch_off.get("x", 0)) if ch_off is not None else 0.0
        cy = float(ch_off.get("y", 0)) if ch_off is not None else 0.0
        cw = float(ch_ext.get("cx", ew or 1)) if ch_ext is not None else (ew or 1.0)
        ch = float(ch_ext.get("cy", eh or 1)) if ch_ext is not None else (eh or 1.0)
        sx = ew / max(cw, 1.0)
        sy = eh / max(ch, 1.0)
        base = _Affine(a=sx, d=sy, e=ox - cx * sx, f=oy - cy * sy)
        rotation = cls._rotation(xfrm)
        flip_h = cls._bool_attr(xfrm, "flipH")
        flip_v = cls._bool_attr(xfrm, "flipV")
        if not rotation and not flip_h and not flip_v:
            return base, rotation
        center_x = ox + ew / 2.0
        center_y = oy + eh / 2.0
        angle = math.radians(rotation)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        fx = -1.0 if flip_h else 1.0
        fy = -1.0 if flip_v else 1.0
        around = _Affine(
            a=cos_a * fx,
            b=sin_a * fx,
            c=-sin_a * fy,
            d=cos_a * fy,
            e=center_x - (cos_a * fx) * center_x - (-sin_a * fy) * center_y,
            f=center_y - (sin_a * fx) * center_x - (cos_a * fy) * center_y,
        )
        return base.then(around), rotation

    @staticmethod
    def _rotation(xfrm: ET.Element | None) -> float:
        if xfrm is None:
            return 0.0
        try:
            return float(xfrm.get("rot", 0)) / 60000.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _rect_percent(node: ET.Element | None) -> dict[str, float]:
        if node is None:
            return {}
        result: dict[str, float] = {}
        for key in ("l", "t", "r", "b"):
            try:
                result[key] = float(node.get(key, 0)) / 100000.0
            except (TypeError, ValueError):
                result[key] = 0.0
        return result

    @staticmethod
    def _alpha(node: ET.Element | None) -> float:
        if node is None:
            return 1.0
        try:
            return max(0.0, min(1.0, float(node.get("amt", 100000)) / 100000.0))
        except (TypeError, ValueError):
            return 1.0

    @staticmethod
    def _first_font_node(node: ET.Element) -> ET.Element | None:
        for path in (
            f".//{{{A_NS}}}rPr",
            f".//{{{A_NS}}}defRPr",
            f".//{{{A_NS}}}endParaRPr",
        ):
            found = node.find(path)
            if found is not None:
                return found
        return None

    @classmethod
    def _text_color(cls, node: ET.Element) -> str:
        for path in (
            f".//{{{A_NS}}}rPr",
            f".//{{{A_NS}}}defRPr",
            f".//{{{A_NS}}}endParaRPr",
        ):
            font_node = node.find(path)
            if font_node is None:
                continue
            value = cls._color(font_node.find(f"{{{A_NS}}}solidFill"))
            if value:
                return value
        return ""

    @staticmethod
    def _font_size(node: ET.Element | None) -> float:
        if node is None:
            return 0.0
        try:
            return float(node.get("sz", 0)) / 100.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _bool_attr(node: ET.Element | None, key: str) -> bool:
        if node is None:
            return False
        return str(node.get(key, "")).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _color(node: ET.Element | None) -> str:
        if node is None:
            return ""
        rgb = node.find(f"{{{A_NS}}}srgbClr")
        if rgb is not None and rgb.get("val"):
            return f"#{rgb.get('val').upper()}"
        scheme = node.find(f"{{{A_NS}}}schemeClr")
        if scheme is not None and scheme.get("val"):
            return f"theme:{scheme.get('val')}"
        return ""

    @classmethod
    def _slide_background(cls, root: ET.Element) -> str:
        fill = root.find(f".//{{{P_NS}}}bg/{{{P_NS}}}bgPr/{{{A_NS}}}solidFill")
        return cls._color(fill) or "#FFFFFF"

    @staticmethod
    def _name(node: ET.Element) -> str:
        nv = node.find(f".//{{{P_NS}}}cNvPr")
        return nv.get("name", "") if nv is not None else ""

    @staticmethod
    def _slide_number(path: str) -> int:
        match = re.search(r"slide(\d+)\.xml$", path)
        return int(match.group(1)) if match else 0
