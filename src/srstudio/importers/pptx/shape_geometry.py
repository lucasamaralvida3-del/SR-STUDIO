from __future__ import annotations

from xml.etree import ElementTree as ET


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
EMU_PER_PX_96 = 9525.0


def shape_geometry_metadata(node: ET.Element) -> dict:
    """Extract the small subset of DrawingML geometry needed by the editor.

    Canva commonly exports rounded rectangles as ``custGeom`` paths rather than
    ``roundRect`` presets. We do not flatten those shapes into bitmap assets;
    instead we recover a conservative corner-radius approximation so the Studio
    can keep the card silhouette close to the original artwork.
    """
    sppr = node.find(f"./{{{P_NS}}}spPr")
    if sppr is None:
        return {}

    line = sppr.find(f"{{{A_NS}}}ln")
    line_width_px = 0.0
    if line is not None:
        try:
            line_width_px = float(line.get("w", 0) or 0) / EMU_PER_PX_96
        except (TypeError, ValueError):
            line_width_px = 0.0

    preset = sppr.find(f"{{{A_NS}}}prstGeom")
    if preset is not None:
        value = str(preset.get("prst") or "")
        metadata = {"shape_geometry": value or "preset"}
        if value == "roundRect":
            metadata["corner_radius_ratio"] = 0.16
        if value == "line":
            metadata["line_width_px"] = max(1.0, line_width_px or 1.0)
        return metadata

    custom = sppr.find(f"{{{A_NS}}}custGeom")
    if custom is None:
        return {"line_width_px": line_width_px} if line_width_px else {}

    metadata = {"shape_geometry": "custom"}
    path = custom.find(f".//{{{A_NS}}}path")
    radius = _rounded_rect_radius(path)
    if radius > 0:
        metadata["corner_radius_ratio"] = radius
    if line_width_px:
        metadata["line_width_px"] = line_width_px
    return metadata


def _rounded_rect_radius(path: ET.Element | None) -> float:
    if path is None:
        return 0.0
    try:
        width = float(path.get("w", 0) or 0)
        height = float(path.get("h", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    if width <= 0 or height <= 0:
        return 0.0

    children = list(path)
    if len(children) < 8 or children[-1].tag.rsplit("}", 1)[-1] != "close":
        return 0.0
    first = children[0]
    if first.tag.rsplit("}", 1)[-1] != "moveTo":
        return 0.0
    point = first.find(f".//{{{A_NS}}}pt")
    if point is None:
        return 0.0
    try:
        first_x = float(point.get("x", 0) or 0)
        first_y = float(point.get("y", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    if abs(first_y) > max(2.0, height * 0.005) or first_x <= 0:
        return 0.0

    cubic_count = sum(child.tag.rsplit("}", 1)[-1] == "cubicBezTo" for child in children)
    line_count = sum(child.tag.rsplit("}", 1)[-1] == "lnTo" for child in children)
    if cubic_count < 4 or line_count < 3:
        return 0.0

    ratio = first_x / max(1.0, min(width, height))
    if not 0.04 <= ratio <= 0.42:
        return 0.0
    return round(min(0.35, max(0.05, ratio)), 4)
