from __future__ import annotations

"""PPTX source provenance and semantic page geometry for SR Graphics Engine 2.

This module is intentionally G2-only.  The shared/legacy PPTX importer keeps the
physical OOXML page ratio exactly as it always did.  Graphics2 may layer an
*intended canvas* on top of that physical size only when package provenance is
strong enough to identify a known Canva export profile.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
import re
import zipfile

from .model import GraphicsDocument

DC_NS = "http://purl.org/dc/elements/1.1/"
CP_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DCTERMS_NS = "http://purl.org/dc/terms/"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

EMU_PER_POINT = 12_700.0
CANVA_4X5_PHYSICAL_EMU = (10_287_000, 12_852_400)
CANVA_4X5_INTENDED_CANVAS = (1080.0, 1350.0)
_CANVA_DESIGN_ID = re.compile(r"^DA[A-Za-z0-9_-]{9}$")

# Stable package markers observed in all three hash-locked Canva sources of the
# G2 visual corpus.  No individual marker is sufficient for detection.
_CANVA_CREATED = "2006-08-16T00:00:00Z"
_CANVA_MODIFIED = "2011-08-01T06:04:30Z"


@dataclass(slots=True, frozen=True)
class PhysicalPageSize:
    width_emu: int
    height_emu: int

    @property
    def width_pt(self) -> float:
        return self.width_emu / EMU_PER_POINT

    @property
    def height_pt(self) -> float:
        return self.height_emu / EMU_PER_POINT

    def to_dict(self) -> dict:
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

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height}


@dataclass(slots=True)
class PptxSourceProfile:
    name: str = "unknown"
    confidence: str = "not_available"
    design_id: str = ""
    physical_page_size: PhysicalPageSize | None = None
    intended_canvas_size: IntendedCanvasSize | None = None
    evidence: list[str] = field(default_factory=list)
    fingerprint_matches: int = 0

    @property
    def reliable_canva(self) -> bool:
        return self.name == "canva" and self.confidence == "reliable"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "confidence": self.confidence,
            "design_id": self.design_id,
            "physical_page_size": self.physical_page_size.to_dict() if self.physical_page_size else None,
            "intended_canvas_size": self.intended_canvas_size.to_dict() if self.intended_canvas_size else None,
            "evidence": list(self.evidence),
            "fingerprint_matches": self.fingerprint_matches,
        }


def inspect_pptx_source_profile(source: str | Path) -> PptxSourceProfile:
    """Inspect package metadata without inferring provenance from aspect ratio.

    RELIABLE Canva requires both a Canva-shaped ``dc:identifier`` and a strong
    multi-field export fingerprint.  A plausible identifier or fingerprint by
    itself is only PARTIAL and never activates a semantic canvas override.
    """

    path = Path(source)
    if path.suffix.lower() != ".pptx" or not path.is_file():
        return PptxSourceProfile()

    try:
        with zipfile.ZipFile(path) as archive:
            core = _xml(archive, "docProps/core.xml")
            app = _xml(archive, "docProps/app.xml")
            presentation = _xml(archive, "ppt/presentation.xml")
    except (OSError, zipfile.BadZipFile, KeyError, ET.ParseError):
        return PptxSourceProfile()

    design_id = _text(core, f"{{{DC_NS}}}identifier")
    physical = _physical_page_size(presentation)
    matches: list[str] = []

    if _text(core, f"{{{DCTERMS_NS}}}created") == _CANVA_CREATED:
        matches.append("core.created.canva-export-epoch")
    if _text(core, f"{{{DCTERMS_NS}}}modified") == _CANVA_MODIFIED:
        matches.append("core.modified.canva-export-epoch")
    if _text(core, f"{{{CP_NS}}}revision") == "1":
        matches.append("core.revision=1")
    if _text(app, f"{{{EP_NS}}}Application") == "Microsoft Office PowerPoint":
        matches.append("app.application=Microsoft Office PowerPoint")
    if _text(app, f"{{{EP_NS}}}AppVersion") == "14.0000":
        matches.append("app.version=14.0000")
    if _text(app, f"{{{EP_NS}}}Slides") == "0":
        matches.append("app.slides=0")
    if _text(app, f"{{{EP_NS}}}PresentationFormat") == "On-screen Show (4:3)":
        matches.append("app.presentation_format=On-screen Show (4:3)")

    identifier_matches = bool(_CANVA_DESIGN_ID.fullmatch(design_id))
    # Requiring six independent package markers in addition to the design ID
    # prevents a generic 4:5 Office deck from being labelled Canva.
    if identifier_matches and len(matches) >= 6:
        confidence = "reliable"
        name = "canva"
        evidence = ["core.dc:identifier=canva-design-id", *matches]
    elif identifier_matches or len(matches) >= 4:
        confidence = "partial"
        name = "canva" if identifier_matches else "unknown"
        evidence = (["core.dc:identifier=canva-design-id"] if identifier_matches else []) + matches
    else:
        confidence = "not_available"
        name = "unknown"
        evidence = matches

    intended: IntendedCanvasSize | None = None
    if (
        name == "canva"
        and confidence == "reliable"
        and physical is not None
        and (physical.width_emu, physical.height_emu) == CANVA_4X5_PHYSICAL_EMU
    ):
        intended = IntendedCanvasSize(*CANVA_4X5_INTENDED_CANVAS)
        evidence.append("geometry.canva-4x5-physical-signature")

    return PptxSourceProfile(
        name=name,
        confidence=confidence,
        design_id=design_id,
        physical_page_size=physical,
        intended_canvas_size=intended,
        evidence=evidence,
        fingerprint_matches=len(matches),
    )


def apply_pptx_page_geometry(document: GraphicsDocument, profile: PptxSourceProfile) -> bool:
    """Apply a semantic intended canvas while preserving physical OOXML size.

    Existing nodes are rescaled into the intended coordinate system.  Later G2
    enrichment passes therefore recover artwork/groups directly against the same
    semantic canvas.  Generic/partial PPTX profiles are metadata-only.
    """

    profile_payload = profile.to_dict()
    document.metadata["pptx_source_profile"] = profile_payload
    changed = False

    for page in document.pages:
        page.metadata["physical_page_size"] = (
            profile.physical_page_size.to_dict() if profile.physical_page_size else None
        )
        page.metadata["source_profile"] = {
            "name": profile.name,
            "confidence": profile.confidence,
            "design_id": profile.design_id,
            "evidence": list(profile.evidence),
        }
        page.metadata["intended_canvas_size"] = (
            profile.intended_canvas_size.to_dict() if profile.intended_canvas_size else None
        )

        intended = profile.intended_canvas_size
        if not profile.reliable_canva or intended is None:
            continue
        old_width = float(page.width)
        old_height = float(page.height)
        if old_width <= 0.0 or old_height <= 0.0:
            continue
        sx = intended.width / old_width
        sy = intended.height / old_height
        if abs(sx - 1.0) > 1e-12 or abs(sy - 1.0) > 1e-12:
            for node in page.nodes.values():
                node.transform.x *= sx
                node.transform.width *= sx
                node.transform.y *= sy
                node.transform.height *= sy
            page.guides_x = [value * sx for value in page.guides_x]
            page.guides_y = [value * sy for value in page.guides_y]
            changed = True
        page.width = intended.width
        page.height = intended.height

    document.metadata["pptx_page_geometry"] = {
        "physical_page_size": profile.physical_page_size.to_dict() if profile.physical_page_size else None,
        "intended_canvas_size": profile.intended_canvas_size.to_dict() if profile.intended_canvas_size else None,
        "source_profile": {
            "name": profile.name,
            "confidence": profile.confidence,
            "design_id": profile.design_id,
        },
        "semantic_override_applied": changed,
    }
    return changed


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    return ET.fromstring(archive.read(name))


def _text(root: ET.Element, tag: str) -> str:
    node = root.find(f".//{tag}")
    return str(node.text or "").strip() if node is not None else ""


def _physical_page_size(presentation: ET.Element) -> PhysicalPageSize | None:
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
    return PhysicalPageSize(width, height)
