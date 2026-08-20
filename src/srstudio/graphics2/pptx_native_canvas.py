from __future__ import annotations

"""Safe PPTX native-canvas resolution for SR Graphics Engine 2.

This module ports only the semantic contract from the historical
``g2/import-canva-native-canvas`` work.  It deliberately does not modify the
shared PPTX reader/import pipeline or the Qt renderer.

A semantic canvas override is allowed only when BOTH conditions hold:

1. the OOXML package carries explicit Canva-origin evidence; and
2. the physical PPTX page matches a known transport signature.

Aspect ratio and filename are never provenance signals.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
import re
import zipfile

DC_NS = "http://purl.org/dc/elements/1.1/"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DCTERMS_NS = "http://purl.org/dc/terms/"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

EMU_PER_POINT = 12_700.0
CANVA_4X5_PHYSICAL_EMU = (10_287_000, 12_852_400)
CANVA_4X5_INTENDED_CANVAS = (1080.0, 1350.0)
CANVA_4X5_PRESET = "canva-4x5-1080x1350"
CANVA_SOURCE_PROFILE = "canva-pptx-export-v1"
_CANVA_DESIGN_ID = re.compile(r"^DA[A-Za-z0-9_-]{9}$")

# Fingerprint measured identically in the three hash-locked G2 corpus decks.
# A generic Office deck matching the physical size is still generic unless this
# independent package-origin evidence is also present.
_CANVA_CREATED = "2006-08-16T00:00:00Z"
_CANVA_MODIFIED = "2011-08-01T06:04:30Z"
_MIN_RELIABLE_FINGERPRINT_MARKERS = 6


@dataclass(slots=True, frozen=True)
class PptxPhysicalPageSize:
    width_emu: int
    height_emu: int

    @property
    def width_pt(self) -> float:
        return self.width_emu / EMU_PER_POINT

    @property
    def height_pt(self) -> float:
        return self.height_emu / EMU_PER_POINT

    def to_dict(self) -> dict[str, int | float]:
        return {
            "width_emu": self.width_emu,
            "height_emu": self.height_emu,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
        }


@dataclass(slots=True, frozen=True)
class IntendedCanvasSize:
    width: float
    height: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(slots=True)
class PptxCanvasResolution:
    pptx_physical_page_size: PptxPhysicalPageSize | None = None
    intended_canvas_size: IntendedCanvasSize | None = None
    source_kind: str = "office-generic"
    source_profile: str = "office-generic"
    source_confidence: str = "not_available"
    source_design_id: str = ""
    source_evidence: list[str] = field(default_factory=list)
    preset: str | None = None
    uses_intended_canvas_size: bool = False
    fingerprint_matches: int = 0

    def to_metadata(self) -> dict[str, object]:
        return {
            "pptx_physical_page_size": (
                self.pptx_physical_page_size.to_dict() if self.pptx_physical_page_size else None
            ),
            "intended_canvas_size": (
                self.intended_canvas_size.to_dict() if self.intended_canvas_size else None
            ),
            "preset": self.preset,
            "source": self.source_kind,
            "source_profile": {
                "name": self.source_profile,
                "confidence": self.source_confidence,
                "design_id": self.source_design_id,
            },
            "origin_evidence": list(self.source_evidence),
            "uses_intended_canvas_size": self.uses_intended_canvas_size,
            "fingerprint_matches": self.fingerprint_matches,
        }


def resolve_pptx_native_canvas(source: str | Path) -> PptxCanvasResolution:
    """Resolve physical size and intended canvas without filename heuristics."""

    path = Path(source)
    if path.suffix.lower() != ".pptx" or not path.is_file():
        return PptxCanvasResolution()

    try:
        with zipfile.ZipFile(path) as archive:
            core = _xml(archive, "docProps/core.xml")
            app = _xml(archive, "docProps/app.xml")
            presentation = _xml(archive, "ppt/presentation.xml")
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError):
        return PptxCanvasResolution()

    physical = _physical_page_size(presentation)
    design_id = _text(core, f"{{{DC_NS}}}identifier")
    fingerprint = _fingerprint_evidence(core, app)
    design_id_matches = bool(_CANVA_DESIGN_ID.fullmatch(design_id))

    if design_id_matches and len(fingerprint) >= _MIN_RELIABLE_FINGERPRINT_MARKERS:
        source_kind = "canva"
        source_profile = CANVA_SOURCE_PROFILE
        confidence = "reliable"
        evidence = [f"core.dc:identifier={design_id}", *fingerprint]
    elif design_id_matches or len(fingerprint) >= 4:
        source_kind = "canva" if design_id_matches else "office-generic"
        source_profile = CANVA_SOURCE_PROFILE if design_id_matches else "office-generic"
        confidence = "partial"
        evidence = ([f"core.dc:identifier={design_id}"] if design_id_matches else []) + fingerprint
    else:
        source_kind = "office-generic"
        source_profile = "office-generic"
        confidence = "not_available"
        evidence = fingerprint

    intended: IntendedCanvasSize | None = None
    preset: str | None = None
    uses_intended = False
    if (
        source_kind == "canva"
        and confidence == "reliable"
        and physical is not None
        and (physical.width_emu, physical.height_emu) == CANVA_4X5_PHYSICAL_EMU
    ):
        intended = IntendedCanvasSize(*CANVA_4X5_INTENDED_CANVAS)
        preset = CANVA_4X5_PRESET
        uses_intended = True
        evidence.append(
            f"physical-page={physical.width_emu}x{physical.height_emu}-emu:known-canva-4x5-transport"
        )

    return PptxCanvasResolution(
        pptx_physical_page_size=physical,
        intended_canvas_size=intended,
        source_kind=source_kind,
        source_profile=source_profile,
        source_confidence=confidence,
        source_design_id=design_id,
        source_evidence=evidence,
        preset=preset,
        uses_intended_canvas_size=uses_intended,
        fingerprint_matches=len(fingerprint),
    )


def _fingerprint_evidence(core: ET.Element, app: ET.Element) -> list[str]:
    evidence: list[str] = []
    if _text(core, f"{{{DCTERMS_NS}}}created") == _CANVA_CREATED:
        evidence.append(f"core.created={_CANVA_CREATED}")
    if _text(core, f"{{{DCTERMS_NS}}}modified") == _CANVA_MODIFIED:
        evidence.append(f"core.modified={_CANVA_MODIFIED}")
    if _text(core, f"{{{CP_NS}}}revision") == "1":
        evidence.append("core.revision=1")
    if _text(app, f"{{{EP_NS}}}Application") == "Microsoft Office PowerPoint":
        evidence.append("app.application=Microsoft Office PowerPoint")
    if _text(app, f"{{{EP_NS}}}AppVersion") == "14.0000":
        evidence.append("app.version=14.0000")
    if _text(app, f"{{{EP_NS}}}Slides") == "0":
        evidence.append("app.slides=0")
    if _text(app, f"{{{EP_NS}}}PresentationFormat") == "On-screen Show (4:3)":
        evidence.append("app.presentation_format=On-screen Show (4:3)")
    return evidence


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(archive.read(name))


def _text(root: ET.Element, tag: str) -> str:
    node = root.find(f".//{tag}")
    return str(node.text or "").strip() if node is not None else ""


def _physical_page_size(presentation: ET.Element) -> PptxPhysicalPageSize | None:
    size = presentation.find(f".//{{{P_NS}}}sldSz")
    if size is None:
        return None
    try:
        width = int(size.get("cx") or 0)
        height = int(size.get("cy") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return PptxPhysicalPageSize(width, height)
