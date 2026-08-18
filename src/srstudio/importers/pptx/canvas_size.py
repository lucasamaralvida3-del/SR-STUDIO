from __future__ import annotations

from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET
import zipfile


EMU_PER_POINT = 12_700
CANVA_4_5_PPTX_PHYSICAL_PT = (810.0, 1012.0)
CANVA_4_5_INTENDED_PX = (1080, 1350)
CANVA_4_5_POINT_TOLERANCE = 0.05


@dataclass(frozen=True, slots=True)
class PptxCanvasResolution:
    """Keep transport geometry distinct from the intended design canvas.

    PPTX coordinates stay in the package's physical EMU coordinate system.  The
    intended canvas is an optional, source-backed pixel size used only when the
    exporter/preset can be identified safely.
    """

    pptx_physical_page_size: dict[str, float | int]
    intended_canvas_size: dict[str, int] | None
    source_kind: str
    source_evidence: tuple[str, ...]
    preset: str | None
    uses_intended_canvas_size: bool

    def to_metadata(self) -> dict:
        data = asdict(self)
        data["source_evidence"] = list(self.source_evidence)
        return data


def _package_text(zf: zipfile.ZipFile, member: str) -> str:
    try:
        raw = zf.read(member)
    except KeyError:
        return ""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return raw.decode("utf-8", errors="ignore")
    parts: list[str] = []
    for node in root.iter():
        if node.text:
            parts.append(node.text)
        for value in node.attrib.values():
            parts.append(value)
    return "\n".join(parts)


def detect_source_kind(zf: zipfile.ZipFile) -> tuple[str, tuple[str, ...]]:
    """Return a conservative package-level source classification.

    A document is marked Canva only when package metadata itself contains an
    explicit Canva marker.  Aspect ratio or filename alone never establishes
    Canva provenance.
    """

    evidence: list[str] = []
    for member in ("docProps/app.xml", "docProps/core.xml", "docProps/custom.xml"):
        text = _package_text(zf, member)
        if "canva" in text.casefold():
            evidence.append(member)
    if evidence:
        return "canva", tuple(evidence)
    return "office-generic", ()


def _points_from_emu(value: int) -> float:
    return float(value) / EMU_PER_POINT


def _matches_canva_4_5_export_signature(width_emu: int, height_emu: int) -> bool:
    width_pt = _points_from_emu(width_emu)
    height_pt = _points_from_emu(height_emu)
    expected_w, expected_h = CANVA_4_5_PPTX_PHYSICAL_PT
    return (
        abs(width_pt - expected_w) <= CANVA_4_5_POINT_TOLERANCE
        and abs(height_pt - expected_h) <= CANVA_4_5_POINT_TOLERANCE
    )


def resolve_canvas_size(
    zf: zipfile.ZipFile,
    width_emu: int,
    height_emu: int,
    *,
    explicit_source_kind: str | None = None,
    explicit_intended_canvas_size: tuple[int, int] | None = None,
) -> PptxCanvasResolution:
    """Resolve physical PPTX geometry and an optional intended pixel canvas.

    Priority is explicit upstream provenance, then conservative package
    detection.  The Canva 4:5 correction is enabled only for the independently
    verified Canva export signature 810 x 1012 pt.  Generic Office documents,
    including documents with a similar aspect ratio, retain the physical PPTX
    ratio.
    """

    detected_kind, evidence = detect_source_kind(zf)
    source_kind = (explicit_source_kind or detected_kind or "office-generic").strip().casefold()
    physical = {
        "width_emu": int(width_emu),
        "height_emu": int(height_emu),
        "width_pt": round(_points_from_emu(width_emu), 6),
        "height_pt": round(_points_from_emu(height_emu), 6),
    }

    intended: dict[str, int] | None = None
    preset: str | None = None

    if explicit_intended_canvas_size is not None and source_kind == "canva":
        width_px, height_px = explicit_intended_canvas_size
        if width_px > 0 and height_px > 0:
            intended = {"width": int(width_px), "height": int(height_px)}
            preset = "explicit-upstream"
    elif source_kind == "canva" and _matches_canva_4_5_export_signature(width_emu, height_emu):
        intended = {
            "width": CANVA_4_5_INTENDED_PX[0],
            "height": CANVA_4_5_INTENDED_PX[1],
        }
        preset = "canva-4:5-1080x1350"

    return PptxCanvasResolution(
        pptx_physical_page_size=physical,
        intended_canvas_size=intended,
        source_kind=source_kind,
        source_evidence=evidence,
        preset=preset,
        uses_intended_canvas_size=intended is not None,
    )
