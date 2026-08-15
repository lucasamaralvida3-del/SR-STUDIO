from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


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
    elements: list[PptxElement] = field(default_factory=list)


@dataclass(slots=True)
class PptxImportResult:
    slides: list[PptxSlide] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PptxImporter:
    """Leitor nativo mínimo de PPTX para preservar geometria, texto e imagens.

    Não renderiza efeitos complexos ainda; sua função é criar uma representação
    estrutural para o Semantic Mapper do Encartes Studio.
    """

    def import_file(self, path: str | Path) -> PptxImportResult:
        result = PptxImportResult()
        with zipfile.ZipFile(Path(path)) as zf:
            slides = sorted(
                (name for name in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=self._slide_number,
            )
            for idx, slide_path in enumerate(slides, start=1):
                try:
                    result.slides.append(self._read_slide(zf, slide_path, idx))
                except Exception as exc:
                    result.warnings.append(f"Slide {idx}: {exc}")
        return result

    def _read_slide(self, zf: zipfile.ZipFile, slide_path: str, index: int) -> PptxSlide:
        root = ET.fromstring(zf.read(slide_path))
        rels = self._relationships(zf, slide_path)
        slide = PptxSlide(index=index)
        sp_tree = root.find(f".//{{{P_NS}}}spTree")
        if sp_tree is None:
            return slide
        for child in list(sp_tree):
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "sp":
                slide.elements.append(self._shape(child))
            elif tag == "pic":
                slide.elements.append(self._picture(child, rels))
            elif tag == "graphicFrame":
                slide.elements.append(self._graphic(child))
            elif tag == "grpSp":
                slide.elements.extend(self._group(child))
        return slide

    def _shape(self, node: ET.Element) -> PptxElement:
        x, y, w, h = self._geometry(node)
        texts = [t.text or "" for t in node.findall(f".//{{{A_NS}}}t")]
        name = self._name(node)
        return PptxElement("text" if texts else "shape", x, y, w, h, "".join(texts).strip(), name=name)

    def _picture(self, node: ET.Element, rels: dict[str, str]) -> PptxElement:
        x, y, w, h = self._geometry(node)
        blip = node.find(f".//{{{A_NS}}}blip")
        rid = blip.get(f"{{{R_NS}}}embed", "") if blip is not None else ""
        return PptxElement("image", x, y, w, h, media_path=rels.get(rid, ""), name=self._name(node))

    def _graphic(self, node: ET.Element) -> PptxElement:
        x, y, w, h = self._geometry(node)
        return PptxElement("graphic", x, y, w, h, name=self._name(node))

    def _group(self, node: ET.Element) -> list[PptxElement]:
        items: list[PptxElement] = []
        for child in list(node):
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "sp":
                item = self._shape(child)
                item.metadata["grouped"] = True
                items.append(item)
            elif tag == "pic":
                x, y, w, h = self._geometry(child)
                items.append(PptxElement("image", x, y, w, h, name=self._name(child), metadata={"grouped": True}))
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
    def _geometry(node: ET.Element) -> tuple[int, int, int, int]:
        xfrm = node.find(f".//{{{A_NS}}}xfrm")
        if xfrm is None:
            return 0, 0, 0, 0
        off = xfrm.find(f"{{{A_NS}}}off")
        ext = xfrm.find(f"{{{A_NS}}}ext")
        return (
            int(off.get("x", 0)) if off is not None else 0,
            int(off.get("y", 0)) if off is not None else 0,
            int(ext.get("cx", 0)) if ext is not None else 0,
            int(ext.get("cy", 0)) if ext is not None else 0,
        )

    @staticmethod
    def _name(node: ET.Element) -> str:
        nv = node.find(f".//{{{P_NS}}}cNvPr")
        return nv.get("name", "") if nv is not None else ""

    @staticmethod
    def _slide_number(path: str) -> int:
        match = re.search(r"slide(\d+)\.xml$", path)
        return int(match.group(1)) if match else 0
