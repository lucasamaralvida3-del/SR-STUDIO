from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import subprocess
import sys
import zipfile
from pathlib import Path

REQUESTED_SHA = "9b3c967c5dad4e5dddee1daa6dd92fab2189437c"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(source_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source_root), *args], text=True).strip()


def rect_values(rect) -> list[float]:
    rect = rect.normalized()
    return [float(rect.x), float(rect.y), float(rect.width), float(rect.height)]


def source_union(rects) -> tuple[float, float, float, float]:
    left = min(float(r[0]) for r in rects)
    top = min(float(r[1]) for r in rects)
    right = max(float(r[0]) + float(r[2]) for r in rects)
    bottom = max(float(r[1]) + float(r[3]) for r in rects)
    return left, top, right - left, bottom - top


def warning_dict(item) -> dict:
    return {
        "code": str(getattr(item, "code", "") or ""),
        "message": str(getattr(item, "message", "") or ""),
        "page_id": str(getattr(item, "page_id", "") or ""),
        "node_id": str(getattr(item, "node_id", "") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    pptx = args.pptx.resolve()
    source_root = args.source_root.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    checked = git(source_root, "rev-parse", "HEAD")
    if checked != REQUESTED_SHA:
        raise RuntimeError(f"Exact SHA mismatch: {checked} != {REQUESTED_SHA}")
    actual_pptx_sha = sha256(pptx)
    if actual_pptx_sha != PPTX_SHA256:
        raise RuntimeError(f"PPTX SHA mismatch: {actual_pptx_sha} != {PPTX_SHA256}")

    source_src = str(source_root / "src")
    sys.path = [source_src, *[p for p in sys.path if Path(p or ".").resolve() != Path.cwd().resolve()]]

    from PIL import Image
    from PySide6.QtGui import QFont, QFontInfo, QImage

    from srstudio.graphics2.fonts import embedded_font_entries, ensure_qgui_application, register_qt_document_fonts
    from srstudio.graphics2.import_bridge import GraphicsImportService
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.model import AssetRef, BindingRole, GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.qt_renderer import render_png
    from srstudio.graphics2.slot_corpus_families import QUINTA3_FAMILY_PRESETS
    from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID, MEAT_STRIP_FULL_CARD_PROFILES
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER, strip_ownership_snapshot

    app = ensure_qgui_application()

    # A — exercise the actual production PPTX import/materialization pipeline.
    imported = GraphicsImportService().import_file(pptx, project_name="Meat Strip diagnostic import")
    imported_doc = imported.document
    production_entries = embedded_font_entries(imported_doc)

    with zipfile.ZipFile(pptx) as archive:
        package_font_parts = sorted(
            name for name in archive.namelist()
            if name.lower().startswith("ppt/fonts/") or name.lower().endswith(".fntdata")
        )

    document = GraphicsDocument(name="Meat Strip exact-SHA runtime diagnostic")
    document.pages = [GraphicsPage(name="Página 1", width=1080.0, height=1350.0, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id

    # Copy only font metadata materialized by production. No parallel font loader.
    direct_fonts = imported_doc.metadata.get("embedded_fonts")
    if isinstance(direct_fonts, list):
        document.metadata["embedded_fonts"] = copy.deepcopy(direct_fonts)
    legacy = imported_doc.metadata.get("legacy_settings")
    if isinstance(legacy, dict) and isinstance(legacy.get("canva_embedded_fonts"), list):
        document.metadata["legacy_settings"] = {
            "canva_embedded_fonts": copy.deepcopy(legacy["canva_embedded_fonts"])
        }

    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)

    # B — materialize exact supervised media before binding, then use the real
    # image_asset_id/image_path product binding path.
    media_dir = out / "official-binding-media"
    media_dir.mkdir(exist_ok=True)
    assets: dict[str, AssetRef] = {}
    paths: dict[str, Path] = {}
    with zipfile.ZipFile(pptx) as archive:
        for profile_id in PROFILE_ORDER:
            spec = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
            internal = str(spec["image_asset"]["internal_media"]).lstrip("/")
            raw = archive.read(internal)
            expected = str(spec["image_asset"]["sha256"])
            actual = hashlib.sha256(raw).hexdigest()
            if actual != expected:
                raise RuntimeError(f"{profile_id}: image SHA mismatch {actual} != {expected}")
            local = media_dir / f"{profile_id}-{Path(internal).name}"
            local.write_bytes(raw)
            asset = AssetRef(kind="image", source=str(local), mime="image/png", sha256=actual, embedded=False)
            document.assets[asset.id] = asset
            assets[profile_id] = asset
            paths[profile_id] = local

    slots = []
    first_cell_before_ownership: list[float] | None = None
    products = {
        "costela": {"id": "pptx-costela", "name": "COSTELA GAÚCHA", "price": "24.86", "unit": "KG"},
        "pernil": {"id": "pptx-pernil", "name": "PERNIL SUINO S/ OSSO", "price": "18.74", "unit": "KG"},
        "musculo": {"id": "pptx-musculo", "name": "MÚSCULO BOVINO", "price": "32.73", "unit": "KG"},
        "moela": {"id": "pptx-moela", "name": "MOELA DE FRANGO", "price": "16.72", "unit": "KG"},
    }
    for profile_id in PROFILE_ORDER:
        result = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        if not result.ok or not result.changed:
            raise RuntimeError(result.to_dict())
        slot = session.page.slots[result.payload["slot_id"]]
        if slot.metadata.get("full_card_profile") != profile_id:
            raise RuntimeError(f"Profile order mismatch: {slot.metadata.get('full_card_profile')} != {profile_id}")
        if profile_id == "costela":
            root = session.page.node(str(slot.metadata.get("root_node_id") or ""))
            if root is not None:
                first_cell_before_ownership = rect_values(root.rect)
        product = dict(products[profile_id])
        product.update({
            "quinta3_supervised_profile": profile_id,
            "image_asset_id": assets[profile_id].id,
            "image_path": str(paths[profile_id]),
        })
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        if not bound.ok or not bound.changed:
            raise RuntimeError(bound.to_dict())
        slots.append(slot)

    strip_ids = {str(slot.metadata.get("meat_strip_root_id") or "") for slot in slots}
    if len(strip_ids) != 1:
        raise RuntimeError(f"Expected one MeatStripRoot, got {strip_ids}")
    strip_id = next(iter(strip_ids))
    snapshot = strip_ownership_snapshot(session.page, strip_id)
    if len(snapshot.get("cell_root_ids") or []) != 4:
        raise RuntimeError(f"Expected 4 ProductCells: {snapshot}")

    image_rows = []
    for profile_id, slot in zip(PROFILE_ORDER, slots):
        node = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
        if node is None:
            raise RuntimeError(f"{profile_id}: IMAGE node missing")
        asset = document.assets.get(node.asset_id)
        source = str(asset.source if asset is not None else "")
        path = Path(source) if source else None
        exists = bool(path and path.is_file())
        qimage = QImage(source) if source else QImage()
        image_rows.append({
            "PROFILE": profile_id.upper(),
            "NODE ID": node.id,
            "VISIBLE": bool(node.visible),
            "PARENT ID": str(node.parent_id or ""),
            "Z INDEX": int(node.z_index),
            "OPACITY": float(node.opacity),
            "ASSET ID": str(node.asset_id or ""),
            "ASSET SOURCE": source,
            "SOURCE EXISTS": exists,
            "SHA256": sha256(path) if exists and path is not None else "",
            "QIMAGE DECODE OK": not qimage.isNull(),
            "QIMAGE WIDTH": int(qimage.width()),
            "QIMAGE HEIGHT": int(qimage.height()),
            "BOUND_IMAGE_SOURCE": str(node.metadata.get("bound_image_source") or ""),
            "PLACEHOLDER": bool(node.metadata.get("placeholder", False)),
            "RECT": rect_values(node.rect),
            "FILL_RECT": copy.deepcopy(node.style.get("fill_rect") or {}),
        })

    # A — register in the same QGuiApplication that render_png reuses.
    registration = register_qt_document_fonts(document)
    app.processEvents()
    info = QFontInfo(QFont("Anton"))
    font_json = {
        "ANTON_REQUESTED": "Anton",
        "ANTON_REGISTERED_FAMILIES": list(registration.families),
        "ANTON_RESOLVED": str(info.family() or ""),
        "ANTON_EXACT_MATCH": bool(info.exactMatch()),
        "PRODUCTION_EMBEDDED_FONT_ENTRIES": production_entries,
        "PPTX_FONT_PARTS": package_font_parts,
        "REGISTRATION_WARNINGS": list(registration.warnings),
        "APPLICATION_NAME": app.applicationName(),
    }
    font_json["CLASSIFICATION"] = (
        "HARNESS GAP"
        if any(str(name).casefold() == "anton" for name in registration.families)
        and font_json["ANTON_EXACT_MATCH"]
        and font_json["ANTON_RESOLVED"].casefold() == "anton"
        else "PRODUCT BUG"
    )
    (out / "meat-strip-font-resolution.json").write_text(
        json.dumps(font_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Normal page render, with all renderer warnings preserved.
    page_render = render_png(document, out / "g2-page.png", target_width=2160)
    warnings = [warning_dict(item) for item in page_render.warnings]
    (out / "meat-strip-render-warnings.json").write_text(
        json.dumps(warnings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not page_render.ok:
        raise RuntimeError("Production page render failed")

    # C — source-vs-runtime geometry, before any diagnostic crop.
    slide_emu = (12192000.0, 15240000.0)
    source_strip = source_union([MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"] for p in PROFILE_ORDER])
    source_norm = [
        source_strip[0] / slide_emu[0] * 1080.0,
        source_strip[1] / slide_emu[1] * 1350.0,
        source_strip[2] / slide_emu[0] * 1080.0,
        source_strip[3] / slide_emu[1] * 1350.0,
    ]
    strip_node = session.page.node(strip_id)
    if strip_node is None:
        raise RuntimeError("MeatStripRoot missing")
    runtime = rect_values(strip_node.rect)
    cells = {}
    for profile_id, slot in zip(PROFILE_ORDER, slots):
        root = session.page.node(str(slot.metadata.get("root_node_id") or ""))
        if root is None:
            raise RuntimeError(f"{profile_id}: ProductCell missing")
        cells[profile_id] = rect_values(root.rect)

    scale_x = runtime[2] / max(source_norm[2], 1e-9)
    scale_y = runtime[3] / max(source_norm[3], 1e-9)
    preset = QUINTA3_FAMILY_PRESETS[MEAT_FAMILY_ID]
    source_costela = MEAT_STRIP_FULL_CARD_PROFILES["costela"]["root_emu"]
    source_costela_norm = [
        float(source_costela[0]) / slide_emu[0] * 1080.0,
        float(source_costela[1]) / slide_emu[1] * 1350.0,
        float(source_costela[2]) / slide_emu[0] * 1080.0,
        float(source_costela[3]) / slide_emu[1] * 1350.0,
    ]
    first_scale_x = cells["costela"][2] / max(source_costela_norm[2], 1e-9)
    first_scale_y = cells["costela"][3] / max(source_costela_norm[3], 1e-9)
    oob = (
        runtime[0] < 0 or runtime[1] < 0
        or runtime[0] + runtime[2] > session.page.width
        or runtime[1] + runtime[3] > session.page.height
    )
    geometry = {
        "PAGE RECT": [0.0, 0.0, float(session.page.width), float(session.page.height)],
        "SOURCE STRIP RECT": list(source_strip),
        "SOURCE STRIP RECT NORMALIZED TO 1080x1350": source_norm,
        "RUNTIME MEAT STRIP ROOT RECT": runtime,
        "RUNTIME / SOURCE SCALE X": scale_x,
        "RUNTIME / SOURCE SCALE Y": scale_y,
        "COSTELA CELL RECT": cells["costela"],
        "PERNIL CELL RECT": cells["pernil"],
        "MUSCULO CELL RECT": cells["musculo"],
        "MOELA CELL RECT": cells["moela"],
        "PRESET WIDTH": float(preset["width"]),
        "PRESET HEIGHT": float(preset["height"]),
        "FIRST CELL BEFORE OWNERSHIP": first_cell_before_ownership,
        "SOURCE COSTELA NORMALIZED": source_costela_norm,
        "FIRST CELL SCALE X": first_scale_x,
        "FIRST CELL SCALE Y": first_scale_y,
        "OUT OF BOUNDS": oob,
        "ORIGIN": {
            "preset": "QUINTA3_FAMILY_PRESETS['quinta3-meat-strip']",
            "resolver": "_resolve_strip_root",
            "formula": "scale_x=cell_rect.width/source_root.width; scale_y=cell_rect.height/source_root.height; strip=source_strip*scale",
        },
    }
    geometry["CLASSIFICATION"] = (
        "PRODUCT BUG"
        if oob
        and math.isclose(scale_x, first_scale_x, rel_tol=1e-6, abs_tol=1e-6)
        and math.isclose(scale_y, first_scale_y, rel_tol=1e-6, abs_tol=1e-6)
        else "HARNESS GAP"
    )

    # Unclipped render: enlarge only the page copy. Never move/resize a node.
    unclip_doc = copy.deepcopy(document)
    unclip_page = unclip_doc.pages[0]
    unclip_page.width = max(unclip_page.width, runtime[0] + runtime[2] + 24.0)
    unclip_page.height = max(unclip_page.height, runtime[1] + runtime[3] + 24.0)
    unclip_report = render_png(
        unclip_doc,
        out / "meat-strip-g2-unclipped.png",
        target_width=max(1, round(unclip_page.width * 2.0)),
    )
    if not unclip_report.ok:
        raise RuntimeError("Unclipped render failed")
    geometry["UNCLIPPED PAGE RECT"] = [0.0, 0.0, float(unclip_page.width), float(unclip_page.height)]
    (out / "meat-strip-runtime-geometry.json").write_text(
        json.dumps(geometry, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Side-by-side entire strip: original crop already produced by the exact-SHA
    # visual harness; candidate is cropped from the enlarged page at unchanged coordinates.
    original_path = out / "meat-strip-original.png"
    if not original_path.is_file():
        raise RuntimeError("Expected meat-strip-original.png from base visual harness")
    original = Image.open(original_path).convert("RGB")
    unclip_full = Image.open(out / "meat-strip-g2-unclipped.png").convert("RGB")
    sx = unclip_full.width / float(unclip_page.width)
    sy = unclip_full.height / float(unclip_page.height)
    box = (
        max(0, math.floor(runtime[0] * sx)),
        max(0, math.floor(runtime[1] * sy)),
        min(unclip_full.width, math.ceil((runtime[0] + runtime[2]) * sx)),
        min(unclip_full.height, math.ceil((runtime[1] + runtime[3]) * sy)),
    )
    candidate = unclip_full.crop(box).convert("RGB")
    candidate = candidate.resize(original.size, Image.Resampling.LANCZOS)
    side = Image.new("RGB", (original.width * 2, original.height), "white")
    side.paste(original, (0, 0))
    side.paste(candidate, (original.width, 0))
    side.save(out / "meat-strip-unclipped-vs-original.png")

    image_warning_nodes = {
        row["node_id"] for row in warnings
        if "IMAGE" in row["code"].upper() or "imagem" in row["message"].casefold()
    }
    all_decode = all(bool(row["QIMAGE DECODE OK"]) for row in image_rows)
    all_bound = all(bool(row["ASSET ID"]) and bool(row["BOUND_IMAGE_SOURCE"]) for row in image_rows)
    image_summary = {
        "ALL QIMAGE DECODE OK": all_decode,
        "ALL OFFICIAL BINDINGS PRESENT": all_bound,
        "IMAGE WARNING NODE IDS": sorted(image_warning_nodes),
        "CLASSIFICATION": "HARNESS GAP" if all_decode and all_bound and not image_warning_nodes else "PRODUCT BUG",
    }
    (out / "meat-strip-image-diagnostics.json").write_text(
        json.dumps({"IMAGES": image_rows, "SUMMARY": image_summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if git(source_root, "status", "--porcelain"):
        raise RuntimeError("Frozen source checkout became dirty")

    print("ANTON_REGISTERED=" + json.dumps(font_json["ANTON_REGISTERED_FAMILIES"], ensure_ascii=False))
    print(f"ANTON_RESOLVED={font_json['ANTON_RESOLVED']}")
    print(f"ANTON_EXACT_MATCH={str(font_json['ANTON_EXACT_MATCH']).lower()}")
    print(f"SCALE_X={scale_x}")
    print(f"SCALE_Y={scale_y}")
    print(f"OUT_OF_BOUNDS={str(oob).lower()}")
    print(f"FONT_CLASSIFICATION={font_json['CLASSIFICATION']}")
    print(f"IMAGE_CLASSIFICATION={image_summary['CLASSIFICATION']}")
    print(f"GEOMETRY_CLASSIFICATION={geometry['CLASSIFICATION']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
