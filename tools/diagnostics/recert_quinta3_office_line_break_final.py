from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

BEFORE_SHA = "2e706558132e8893377c0dd6772d55c6c9d3a739"
AFTER_SHA = "86713080e5378bcc792a8fdb8a765a4202b1c8f4"
PPTX_SHA = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
PROFILES = ("costela", "pernil", "musculo", "moela")
PRODUCTS = {
    "costela": {"id": "recert-costela", "name": "COSTELA GAÚCHA", "price": "24.86", "unit": "KG"},
    "pernil": {"id": "recert-pernil", "name": "PERNIL SUINO S/ OSSO", "price": "18.74", "unit": "KG"},
    "musculo": {"id": "recert-musculo", "name": "MÚSCULO BOVINO", "price": "32.73", "unit": "KG"},
    "moela": {"id": "recert-moela", "name": "MOELA DE FRANGO", "price": "16.72", "unit": "KG"},
}
ROLE_NAMES = ("currency", "decimal", "unit", "integer", "name")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _font_for(node, QtGui, qt_renderer):
    style = node.style
    family = str(style.get("font_family") or style.get("source_font_family") or "Segoe UI")
    size = max(1.0, float(style.get("font_size") or 20.0))
    unit = str(style.get("font_size_unit") or "pt").lower()
    pixel_size = size * 96.0 / 72.0 if unit in {"pt", "point", "points"} else size
    font = QtGui.QFont(family)
    font.setPixelSize(max(1, round(pixel_size)))
    qt_renderer._set_font_weight(font, style.get("font_weight"), QtGui)
    font.setItalic(bool(style.get("italic")))
    if style.get("letter_spacing") not in (None, ""):
        font.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, float(style.get("letter_spacing") or 0.0))
    return font


def _build_meat_document():
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.model import GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID

    document = GraphicsDocument(name="Final Office line-break exact recert")
    document.pages = [GraphicsPage(name="Página 1", width=1080.0, height=1350.0, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)
    slots = []
    for profile in PROFILES:
        added = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        if not added.ok or not added.changed:
            raise RuntimeError(f"failed to add Meat slot: {profile}: {added.message}")
        slot = session.page.slots[added.payload["slot_id"]]
        product = dict(PRODUCTS[profile])
        product["quinta3_supervised_profile"] = profile
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        if not bound.ok or not bound.changed:
            raise RuntimeError(f"failed to bind Meat slot: {profile}: {bound.message}")
        slots.append((profile, slot))
    return document, session, slots


def _role_nodes(session, slots):
    from srstudio.graphics2.model import BindingRole

    bindings = {
        "currency": BindingRole.CURRENCY,
        "decimal": BindingRole.PRICE_CENTS,
        "unit": BindingRole.UNIT,
        "integer": BindingRole.PRICE_REAIS,
        "name": BindingRole.NAME,
        "image": BindingRole.IMAGE,
    }
    return {
        profile: {key: session.page.node(slot.node_by_role[binding.value]) for key, binding in bindings.items()}
        for profile, slot in slots
    }


def _layout_info(node, QtCore, QtGui, qt_renderer):
    font = _font_for(node, QtGui, qt_renderer)
    rect = QtCore.QRectF(0.0, 0.0, node.rect.width, node.rect.height)
    text = str(node.text or "")
    wrapped = qt_renderer._pptx_shape_autofit_wrapped_layout(text, rect, node.style, font, QtCore, QtGui)
    single = qt_renderer._pptx_shape_autofit_single_line_layout(text, rect, node.style, font, QtGui)
    if wrapped is not None:
        segments = [str(item[0]) for item in wrapped]
        baselines = [float(item[2]) for item in wrapped]
        route = "shape_autofit_wrapped"
    elif single is not None:
        segments = [text]
        baselines = [float(single[1])]
        route = "shape_autofit_explicit_baseline"
    else:
        segments, baselines, route = [text], [], "qt_rect_fallback"
    latin = getattr(qt_renderer, "_pptx_effective_latin_line_break", lambda _style: None)(node.style)
    overflow = getattr(qt_renderer, "_pptx_effective_horizontal_overflow", lambda _style: None)(node.style)
    return {
        "TEXT": text,
        "ROUTE": route,
        "SEGMENTS": segments,
        "LINE_COUNT": len(segments) if wrapped is not None or single is not None else 0,
        "BASELINE_COUNT": len(baselines),
        "BASELINES": baselines,
        "LATIN_LINE_BREAK_EFFECTIVE": latin,
        "HORIZONTAL_OVERFLOW_EFFECTIVE": overflow,
        "PPTX_WRAP": str(node.style.get("pptx_wrap") or ""),
        "PPTX_AUTOFIT": str(node.style.get("pptx_auto_fit") or ""),
    }


def _save_probe(node, output: Path, QtCore, QtGui, qt_renderer):
    rect = node.rect.normalized()
    pad = 32
    image = QtGui.QImage(
        max(8, int(math.ceil(rect.width)) + pad * 2),
        max(8, int(math.ceil(rect.height)) + pad * 2 + 50),
        QtGui.QImage.Format_ARGB32_Premultiplied,
    )
    image.fill(QtGui.QColor("#FFFFFF"))
    painter = QtGui.QPainter(image)
    qt_renderer._configure_painter(painter, QtGui)
    clone = node.clone(preserve_id=True)
    clone.transform.x = float(pad)
    clone.transform.y = float(pad)
    try:
        qt_renderer._draw_text(painter, clone, QtCore, QtGui)
    finally:
        painter.end()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(output), "PNG", 100):
        raise RuntimeError(f"could not save probe: {output}")


def _crop_box(node, width: int, height: int) -> list[int]:
    rect = node.rect.normalized()
    return [
        max(0, int(math.floor(rect.x)) - 3),
        max(0, int(math.floor(rect.y)) - 3),
        min(width, int(math.ceil(rect.right)) + 3),
        min(height, int(math.ceil(rect.bottom)) + 24),
    ]


def _dominant_rgb(image):
    counts = {}
    for pixel in image.convert("RGB").getdata():
        counts[pixel] = counts.get(pixel, 0) + 1
    return max(counts, key=counts.get)


def _components(image, threshold: int = 38):
    rgb = image.convert("RGB")
    width, height = rgb.size
    background = _dominant_rgb(rgb)
    pixels = rgb.load()
    mask = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            color = pixels[x, y]
            mask[y][x] = max(abs(int(color[i]) - int(background[i])) for i in range(3)) >= threshold
    seen = [[False] * width for _ in range(height)]
    rows = []
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or seen[y][x]:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            points = []
            while stack:
                cx, cy = stack.pop()
                points.append((cx, cy))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < width and 0 <= ny < height and mask[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            if len(points) < 5:
                continue
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            box = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
            if box[1] == 0 and box[2] - box[0] > width * 0.45:
                continue
            rows.append(
                {
                    "AREA": len(points),
                    "BBOX": box,
                    "CENTROID_X": sum(xs) / len(xs),
                    "CENTROID_Y": sum(ys) / len(ys),
                    "BASELINE_PROXY_Y": float(max(ys)),
                }
            )
    return rows, list(background)


def _cluster_lines(image):
    components, background = _components(image)
    if not components:
        return {"CLUSTER_COUNT": 0, "CLUSTERS": [], "COMPONENTS": [], "BACKGROUND_RGB": background}
    heights = sorted(max(1, row["BBOX"][3] - row["BBOX"][1]) for row in components)
    tolerance = max(4.0, min(6.0, heights[len(heights) // 2] * 0.42))
    groups = []
    for component in sorted(components, key=lambda row: row["BASELINE_PROXY_Y"]):
        choices = [
            (abs(component["BASELINE_PROXY_Y"] - max(item["BASELINE_PROXY_Y"] for item in group)), index)
            for index, group in enumerate(groups)
        ]
        choices = [choice for choice in choices if choice[0] <= tolerance]
        if choices:
            groups[min(choices)[1]].append(component)
        else:
            groups.append([component])
    clusters = []
    for group in groups:
        area = sum(row["AREA"] for row in group)
        clusters.append(
            {
                "CENTROID_Y": sum(row["CENTROID_Y"] * row["AREA"] for row in group) / area,
                "BASELINE_PROXY_Y": max(row["BASELINE_PROXY_Y"] for row in group),
                "COMPONENT_COUNT": len(group),
                "BBOX": [
                    min(row["BBOX"][0] for row in group),
                    min(row["BBOX"][1] for row in group),
                    max(row["BBOX"][2] for row in group),
                    max(row["BBOX"][3] for row in group),
                ],
            }
        )
    clusters.sort(key=lambda row: row["BASELINE_PROXY_Y"])
    return {
        "CLUSTER_COUNT": len(clusters),
        "CLUSTER_Y": [row["CENTROID_Y"] for row in clusters],
        "CLUSTER_BASELINE_Y": [row["BASELINE_PROXY_Y"] for row in clusters],
        "CLUSTERS": clusters,
        "COMPONENTS": components,
        "BACKGROUND_RGB": background,
        "BASELINE_TOLERANCE": tolerance,
    }


def _overlay(image, topology, path: Path):
    from PIL import ImageDraw

    result = image.convert("RGB").copy()
    draw = ImageDraw.Draw(result)
    colors = ("#00ff00", "#00ffff", "#ff00ff")
    for component in topology.get("COMPONENTS", []):
        draw.rectangle(tuple(component["BBOX"]), outline="#ff8800")
    for index, cluster in enumerate(topology.get("CLUSTERS", [])):
        color = colors[index % len(colors)]
        y = int(round(cluster["BASELINE_PROXY_Y"]))
        draw.line((0, y, result.width - 1, y), fill=color)
        draw.text((2, max(0, y - 10)), f"L{index + 1}", fill=color)
    path.parent.mkdir(parents=True, exist_ok=True)
    result.resize((result.width * 6, result.height * 6)).save(path)


def _font_gate(pptx: Path):
    from PySide6 import QtGui
    from srstudio.graphics2.fonts import register_qt_document_fonts
    from srstudio.graphics2.import_bridge import GraphicsImportService

    payload = {"IMPORT_OK": False, "ANTON_EXACT": False, "REGISTERED_FAMILIES": [], "WARNINGS": []}
    try:
        imported = GraphicsImportService().import_file(pptx, project_name="Exact recert font import")
        report = register_qt_document_fonts(imported.document)
        info = QtGui.QFontInfo(QtGui.QFont("Anton"))
        payload.update(
            {
                "IMPORT_OK": True,
                "ANTON_EXACT": bool(info.exactMatch() and str(info.family()).casefold() == "anton"),
                "RESOLVED_FAMILY": str(info.family()),
                "REGISTERED_FAMILIES": list(report.families),
                "WARNINGS": list(report.warnings),
            }
        )
    except Exception as exc:
        payload["ERROR"] = repr(exc)
    return payload


def probe(args) -> int:
    if sha256(args.pptx) != PPTX_SHA:
        raise RuntimeError("exact PPTX SHA mismatch")
    sys.path.insert(0, str(args.source_root.resolve() / "src"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image
    from PySide6 import QtCore, QtGui
    from srstudio.graphics2 import qt_renderer
    from srstudio.graphics2.fonts import ensure_qgui_application
    from srstudio.graphics2.qt_renderer import render_png
    from srstudio.graphics2.slot_corpus_full_card import meat_full_card_profile
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import ownership_snapshot

    app = ensure_qgui_application()
    app.processEvents()
    font = _font_gate(args.pptx)
    document, session, slots = _build_meat_document()
    nodes = _role_nodes(session, slots)
    args.out.mkdir(parents=True, exist_ok=True)
    page_path = args.out / "meat-page.png"
    report = render_png(document, page_path, target_width=1080)
    page_image = Image.open(page_path).convert("RGB")
    roles, images, ownership = {}, {}, {}
    for profile, slot in slots:
        roles[profile] = {}
        ownership[profile] = ownership_snapshot(session.page, slot)
        for role in ROLE_NAMES:
            node = nodes[profile][role]
            info = _layout_info(node, QtCore, QtGui, qt_renderer)
            probe_path = args.out / "probes" / f"{profile}-{role}.png"
            _save_probe(node, probe_path, QtCore, QtGui, qt_renderer)
            info["PROBE_SHA256"] = sha256(probe_path)
            info["NODE_RECT"] = [node.rect.x, node.rect.y, node.rect.width, node.rect.height]
            if role == "decimal":
                box = _crop_box(node, page_image.width, page_image.height)
                crop = page_image.crop(tuple(box))
                crop_path = args.out / "decimal-crops" / f"{profile}.png"
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                crop.save(crop_path)
                info["CROP_BOX"] = box
                info["VISUAL_TOPOLOGY"] = _cluster_lines(crop)
                _overlay(crop, info["VISUAL_TOPOLOGY"], args.out / "decimal-overlays" / f"{profile}.png")
            roles[profile][role] = info
        image_node = nodes[profile]["image"]
        expected_fill = dict(meat_full_card_profile(profile)["image_asset"]["fill_rect"])
        actual_fill = dict(image_node.style.get("fill_rect") or {})
        images[profile] = {
            "SOURCE_IMAGE_SHA256": str(image_node.metadata.get("image_sha256") or ""),
            "INTERNAL_MEDIA": str(image_node.metadata.get("pptx_internal_media") or ""),
            "FILL_RECT": actual_fill,
            "EXPECTED_FILL_RECT": expected_fill,
            "FILL_RECT_PRESERVED": actual_fill == expected_fill,
        }
    payload = {
        "LABEL": args.label,
        "PPTX_SHA256": sha256(args.pptx),
        "FONT": font,
        "ROLES": roles,
        "IMAGES": images,
        "OWNERSHIP": ownership,
        "RENDER_WARNINGS": [warning.message for warning in report.warnings],
        "PAGE_SHA256": sha256(page_path),
    }
    (args.out / "probe-summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _image_metrics(reference, rendered):
    if reference.size != rendered.size:
        return {"SIZE_MATCH": False, "MAE": None, "CHANGED_RATIO": None}
    left = list(reference.convert("RGB").getdata())
    right = list(rendered.convert("RGB").getdata())
    total = max(1, len(left))
    delta_sum = 0
    changed = 0
    for a, b in zip(left, right):
        delta = sum(abs(int(a[i]) - int(b[i])) for i in range(3))
        delta_sum += delta
        changed += int(delta > 0)
    return {"SIZE_MATCH": True, "MAE": delta_sum / (total * 3), "CHANGED_RATIO": changed / total}


def compare(args) -> int:
    from PIL import Image

    before = json.loads((args.before / "probe-summary.json").read_text(encoding="utf-8"))
    after = json.loads((args.after / "probe-summary.json").read_text(encoding="utf-8"))
    reference = Image.open(args.reference).convert("RGB")
    after_page = Image.open(args.after / "meat-page.png").convert("RGB")
    if reference.size != after_page.size:
        raise RuntimeError(f"reference size {reference.size} != AFTER page {after_page.size}")
    reference_topology, visual_metrics = {}, {}
    for profile in PROFILES:
        box = after["ROLES"][profile]["decimal"]["CROP_BOX"]
        ref_crop = reference.crop(tuple(box))
        aft_crop = after_page.crop(tuple(box))
        reference_topology[profile] = _cluster_lines(ref_crop)
        visual_metrics[profile] = _image_metrics(ref_crop, aft_crop)
        _overlay(ref_crop, reference_topology[profile], args.out / "reference-overlays" / f"{profile}.png")
    currency = all(after["ROLES"][p]["currency"]["LINE_COUNT"] == 2 and after["ROLES"][p]["currency"]["BASELINE_COUNT"] == 2 for p in PROFILES)
    decimal = all(after["ROLES"][p]["decimal"]["LINE_COUNT"] == 2 and after["ROLES"][p]["decimal"]["BASELINE_COUNT"] == 2 for p in PROFILES)
    unit = all(
        after["ROLES"][p]["unit"]["LINE_COUNT"] == 1
        and after["ROLES"][p]["unit"]["BASELINE_COUNT"] == 1
        and after["ROLES"][p]["unit"]["LATIN_LINE_BREAK_EFFECTIVE"] is False
        and after["ROLES"][p]["unit"]["HORIZONTAL_OVERFLOW_EFFECTIVE"] == "overflow"
        for p in PROFILES
    )
    integer = all(after["ROLES"][p]["integer"]["ROUTE"] == "shape_autofit_explicit_baseline" and before["ROLES"][p]["integer"]["PROBE_SHA256"] == after["ROLES"][p]["integer"]["PROBE_SHA256"] for p in PROFILES)
    name = all(after["ROLES"][p]["name"]["ROUTE"] == "shape_autofit_explicit_baseline" and before["ROLES"][p]["name"]["PROBE_SHA256"] == after["ROLES"][p]["name"]["PROBE_SHA256"] for p in PROFILES)
    reference_clusters = {p: reference_topology[p]["CLUSTER_COUNT"] for p in PROFILES}
    after_clusters = {p: after["ROLES"][p]["decimal"]["VISUAL_TOPOLOGY"]["CLUSTER_COUNT"] for p in PROFILES}
    topology = all(reference_clusters[p] == 2 and after_clusters[p] == 2 for p in PROFILES)
    images = all(bool(after["IMAGES"][p]["SOURCE_IMAGE_SHA256"]) and bool(after["IMAGES"][p]["INTERNAL_MEDIA"]) for p in PROFILES)
    ownership = all(after["OWNERSHIP"][p]["role"] == "product_cell" and after["OWNERSHIP"][p]["parent_id"] == after["OWNERSHIP"][p]["strip_root_id"] and bool(after["OWNERSHIP"][p]["strip_root_id"]) for p in PROFILES)
    result = {
        "BEFORE_SHA": BEFORE_SHA,
        "AFTER_SHA": AFTER_SHA,
        "PPTX_SHA256": PPTX_SHA,
        "CURRENCY": currency,
        "DECIMAL": decimal,
        "UNIT": unit,
        "INTEGER": integer,
        "NAME": name,
        "REFERENCE_DECIMAL_CLUSTERS": reference_clusters,
        "AFTER_DECIMAL_CLUSTERS": after_clusters,
        "DECIMAL_TOPOLOGY": topology,
        "VISUAL_METRICS_SECONDARY": visual_metrics,
        "FONT_ANTON_EXACT": bool(after["FONT"].get("ANTON_EXACT")),
        "IMAGES_4_OF_4": images,
        "MUSCULO_FILL_RECT_PRESERVED": bool(after["IMAGES"]["musculo"]["FILL_RECT_PRESERVED"]),
        "OWNERSHIP": ownership,
        "PRODUCTION_FILES_CHANGED_IN_DIAGNOSTIC_PR": 0,
    }
    result["PRIMARY_GATES_PASS"] = all(result[key] for key in ("CURRENCY", "DECIMAL", "UNIT", "INTEGER", "NAME", "DECIMAL_TOPOLOGY", "FONT_ANTON_EXACT", "IMAGES_4_OF_4", "MUSCULO_FILL_RECT_PRESERVED", "OWNERSHIP"))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "final-recert-summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["PRIMARY_GATES_PASS"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--label", required=True, choices=("before", "after"))
    p.add_argument("--source-root", required=True, type=Path)
    p.add_argument("--pptx", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    c = sub.add_parser("compare")
    c.add_argument("--before", required=True, type=Path)
    c.add_argument("--after", required=True, type=Path)
    c.add_argument("--reference", required=True, type=Path)
    c.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    return probe(args) if args.command == "probe" else compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
