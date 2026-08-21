from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops, ImageEnhance, ImageStat

REQUESTED_SHA = "9b3c967c5dad4e5dddee1daa6dd92fab2189437c"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
PPTX_NAME = "OFERTAS QUINTA FILÉ NOVO (3).pptx"
PRODUCTS = {
    "costela": {"id": "pptx-costela", "name": "COSTELA GAÚCHA", "price": "24.86", "unit": "KG"},
    "pernil": {"id": "pptx-pernil", "name": "PERNIL SUINO S/ OSSO", "price": "18.74", "unit": "KG"},
    "musculo": {"id": "pptx-musculo", "name": "MÚSCULO BOVINO", "price": "32.73", "unit": "KG"},
    "moela": {"id": "pptx-moela", "name": "MOELA DE FRANGO", "price": "16.72", "unit": "KG"},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(source_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source_root), *args], text=True).strip()


def assert_exact_source(source_root: Path) -> str:
    checked = run_git(source_root, "rev-parse", "HEAD")
    print(f"REQUESTED_SHA={REQUESTED_SHA}")
    print(f"CHECKED_OUT_SHA={checked}")
    if checked != REQUESTED_SHA:
        raise SystemExit(f"Exact SHA gate failed: {checked} != {REQUESTED_SHA}")
    if run_git(source_root, "status", "--porcelain"):
        raise SystemExit("Exact SHA checkout is not clean before render")
    return checked


def pptx_slide_size(pptx: Path) -> tuple[int, int]:
    with zipfile.ZipFile(pptx) as archive:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    size = root.find("p:sldSz", ns)
    if size is None:
        raise RuntimeError("PPTX slide size missing")
    return int(size.attrib["cx"]), int(size.attrib["cy"])


def find_soffice() -> str:
    candidates = [
        shutil.which("soffice"),
        shutil.which("soffice.exe"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("LibreOffice/soffice not found; cannot rasterize PPTX ground truth directly")


def render_pptx_page(pptx: Path, out_dir: Path, *, dpi: int = 192) -> Path:
    soffice = find_soffice()
    reference_dir = out_dir / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(reference_dir), str(pptx)],
        check=True,
        timeout=180,
    )
    pdf = reference_dir / (pptx.stem + ".pdf")
    if not pdf.is_file():
        raise RuntimeError(f"LibreOffice did not create {pdf}")
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    if len(doc) != 1:
        raise RuntimeError(f"Expected one PPTX slide, got {len(doc)}")
    bitmap = doc[0].render(scale=float(dpi) / 72.0)
    image = bitmap.to_pil().convert("RGB")
    target = reference_dir / "pptx-page.png"
    image.save(target)
    return target


def rect_union(rects):
    left = min(float(r[0]) for r in rects)
    top = min(float(r[1]) for r in rects)
    right = max(float(r[0]) + float(r[2]) for r in rects)
    bottom = max(float(r[1]) + float(r[3]) for r in rects)
    return (left, top, right - left, bottom - top)


def relative_rect(parent, rel):
    return (
        float(parent[0]) + float(rel[0]) * float(parent[2]),
        float(parent[1]) + float(rel[1]) * float(parent[3]),
        float(rel[2]) * float(parent[2]),
        float(rel[3]) * float(parent[3]),
    )


def union_two(a, b):
    left = min(a[0], b[0]); top = min(a[1], b[1])
    right = max(a[0] + a[2], b[0] + b[2]); bottom = max(a[1] + a[3], b[1] + b[3])
    return (left, top, right - left, bottom - top)


def crop_from_logical(image: Image.Image, rect, logical_width: float, logical_height: float) -> Image.Image:
    sx = image.width / float(logical_width)
    sy = image.height / float(logical_height)
    left = max(0, math.floor(float(rect[0]) * sx))
    top = max(0, math.floor(float(rect[1]) * sy))
    right = min(image.width, math.ceil((float(rect[0]) + float(rect[2])) * sx))
    bottom = min(image.height, math.ceil((float(rect[1]) + float(rect[3])) * sy))
    if right <= left or bottom <= top:
        raise RuntimeError(f"Invalid crop: {rect}")
    return image.crop((left, top, right, bottom))


def normalize_pair(reference: Image.Image, candidate: Image.Image) -> tuple[Image.Image, Image.Image]:
    ref = reference.convert("RGB")
    cand = candidate.convert("RGB")
    if cand.size != ref.size:
        cand = cand.resize(ref.size, Image.Resampling.LANCZOS)
    return ref, cand


def diff_image(reference: Image.Image, candidate: Image.Image) -> Image.Image:
    ref, cand = normalize_pair(reference, candidate)
    diff = ImageChops.difference(ref, cand)
    return ImageEnhance.Contrast(diff).enhance(4.0)


def pixel_metrics(reference: Image.Image, candidate: Image.Image, tolerance: int = 16) -> dict:
    ref, cand = normalize_pair(reference, candidate)
    diff = ImageChops.difference(ref, cand)
    stat = ImageStat.Stat(diff)
    mae = sum(stat.mean) / len(stat.mean)
    rms = math.sqrt(sum(value * value for value in stat.rms) / len(stat.rms))
    extrema = diff.getextrema()
    max_abs = max(channel[1] for channel in extrema)
    gray = diff.convert("L")
    hist = gray.histogram()
    changed = sum(hist[tolerance + 1 :])
    total = max(1, ref.width * ref.height)
    return {
        "width": ref.width,
        "height": ref.height,
        "pixel_tolerance": tolerance,
        "mae": round(float(mae), 6),
        "rmse": round(float(rms), 6),
        "max_abs": int(max_abs),
        "changed_ratio": round(changed / total, 8),
    }


def severity(changed_ratio: float) -> str:
    if changed_ratio >= 0.30:
        return "HIGH"
    if changed_ratio >= 0.10:
        return "MEDIUM"
    if changed_ratio > 0:
        return "LOW"
    return "NONE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    pptx = args.pptx.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    checked = assert_exact_source(source_root)
    actual_pptx_sha = sha256(pptx)
    print(f"PPTX_SHA256={actual_pptx_sha}")
    if pptx.name != PPTX_NAME or actual_pptx_sha != PPTX_SHA256:
        raise SystemExit(f"PPTX gate failed: name={pptx.name!r}, sha256={actual_pptx_sha}")

    # Force imports to the frozen checkout, never the diagnostic branch copy.
    source_src = str(source_root / "src")
    sys.path = [source_src, *[p for p in sys.path if Path(p or ".").resolve() != Path.cwd().resolve()]]

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFont, QFontInfo
    from srstudio.graphics2.fonts import ensure_qgui_application, register_qt_document_fonts
    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.model import AssetRef, BindingRole, GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.qt_renderer import render_png
    from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID, MEAT_STRIP_FULL_CARD_PROFILES
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER, strip_ownership_snapshot

    app = ensure_qgui_application()
    document = GraphicsDocument(name="Quinta3 Meat Strip visual certification")
    document.pages = [GraphicsPage(name="Página 1", width=1080.0, height=1350.0, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)
    slots = []
    for profile_id in PROFILE_ORDER:
        result = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        if not result.ok or not result.changed:
            raise RuntimeError(result.to_dict())
        slot = session.page.slots[result.payload["slot_id"]]
        if slot.metadata.get("full_card_profile") != profile_id:
            raise RuntimeError(f"Profile order mismatch: {slot.metadata.get('full_card_profile')} != {profile_id}")
        product = dict(PRODUCTS[profile_id])
        product["quinta3_supervised_profile"] = profile_id
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        if not bound.ok or not bound.changed:
            raise RuntimeError(bound.to_dict())
        slots.append(slot)

    strip_ids = {str(slot.metadata.get("meat_strip_root_id") or "") for slot in slots}
    if len(strip_ids) != 1 or len(slots) != 4:
        raise RuntimeError(f"Ownership gate failed: strip_roots={strip_ids}, cells={len(slots)}")
    strip_id = next(iter(strip_ids))
    snapshot = strip_ownership_snapshot(session.page, strip_id)
    if len(snapshot.get("cell_root_ids") or []) != 4:
        raise RuntimeError(f"Expected 4 ProductCells: {snapshot}")

    # Materialize the exact PPTX picture-fill media into temporary local assets.
    media_dir = out / "pptx-media"
    media_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(pptx) as archive:
        for profile_id, slot in zip(PROFILE_ORDER, slots):
            spec = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
            internal = str(spec["image_asset"]["internal_media"]).lstrip("/")
            raw = archive.read(internal)
            expected_asset_sha = str(spec["image_asset"]["sha256"])
            actual_asset_sha = hashlib.sha256(raw).hexdigest()
            if actual_asset_sha != expected_asset_sha:
                raise RuntimeError(f"{profile_id} media SHA mismatch: {actual_asset_sha} != {expected_asset_sha}")
            local = media_dir / Path(internal).name
            local.write_bytes(raw)
            asset = AssetRef(kind="image", source=str(local), mime="image/png", sha256=actual_asset_sha, embedded=False)
            document.assets[asset.id] = asset
            image_node = session.page.node(slot.node_by_role[BindingRole.IMAGE.value])
            if image_node is None:
                raise RuntimeError(f"IMAGE node missing for {profile_id}")
            image_node.asset_id = asset.id

    musculo_slot = slots[2]
    musculo_node = session.page.node(musculo_slot.node_by_role[BindingRole.IMAGE.value])
    expected_fill = {"l": 0.0, "t": -0.10057, "r": 0.0, "b": -0.40571}
    actual_fill = {k: float((musculo_node.style.get("fill_rect") or {}).get(k, 0.0)) for k in ("l", "t", "r", "b")}
    if any(not math.isclose(actual_fill[k], expected_fill[k], abs_tol=1e-9) for k in expected_fill):
        raise RuntimeError(f"MUSCULO fillRect mismatch: {actual_fill}")

    # Same QGuiApplication is used by font registration, QFontInfo and render_png.
    font_registration = register_qt_document_fonts(document)
    requested_font = QFont("Anton")
    font_info = QFontInfo(requested_font)
    font_payload = {
        "requested": "Anton",
        "resolved": font_info.family(),
        "exactMatch": bool(font_info.exactMatch()),
        "styleName": font_info.styleName(),
        "applicationName": app.applicationName(),
        "registeredFamilies": font_registration.families,
        "registrationWarnings": font_registration.warnings,
    }
    (out / "meat-strip-font-resolution.json").write_text(json.dumps(font_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ANTON_REQUESTED=Anton")
    print(f"ANTON_RESOLVED={font_payload['resolved']}")
    print(f"ANTON_EXACT_MATCH={str(font_payload['exactMatch']).lower()}")

    full_g2 = out / "g2-page.png"
    render = render_png(document, full_g2, target_width=2160)
    if not render.ok:
        raise RuntimeError("Qt/G2 render did not produce a PNG")

    original_page = render_pptx_page(pptx, out)
    original_full = Image.open(original_page).convert("RGB")
    g2_full = Image.open(full_g2).convert("RGB")
    slide_w, slide_h = pptx_slide_size(pptx)
    source_roots = [MEAT_STRIP_FULL_CARD_PROFILES[p]["root_emu"] for p in PROFILE_ORDER]
    source_strip = rect_union(source_roots)
    strip_node = session.page.node(strip_id)
    if strip_node is None:
        raise RuntimeError("MeatStripRoot missing after render")
    runtime_strip = strip_node.rect.normalized()
    runtime_strip_tuple = (runtime_strip.x, runtime_strip.y, runtime_strip.width, runtime_strip.height)

    original = crop_from_logical(original_full, source_strip, slide_w, slide_h)
    candidate = crop_from_logical(g2_full, runtime_strip_tuple, session.page.width, session.page.height)
    original.save(out / "meat-strip-original.png")
    candidate.save(out / "meat-strip-g2.png")
    ref_norm, cand_norm = normalize_pair(original, candidate)
    side = Image.new("RGB", (ref_norm.width * 2, ref_norm.height), "white")
    side.paste(ref_norm, (0, 0)); side.paste(cand_norm, (ref_norm.width, 0))
    side.save(out / "meat-strip-original-vs-g2.png")
    diff_image(original, candidate).save(out / "meat-strip-diff.png")

    # Músculo IMAGE raster comparison specifically verifies the non-zero fillRect effect.
    musculo_profile = MEAT_STRIP_FULL_CARD_PROFILES["musculo"]
    source_musculo_image = relative_rect(musculo_profile["root_emu"], musculo_profile["roles"]["image"]["relative"])
    runtime_musculo = musculo_node.rect.normalized()
    runtime_musculo_image = (runtime_musculo.x, runtime_musculo.y, runtime_musculo.width, runtime_musculo.height)
    mus_orig = crop_from_logical(original_full, source_musculo_image, slide_w, slide_h)
    mus_g2 = crop_from_logical(g2_full, runtime_musculo_image, session.page.width, session.page.height)
    mus_orig.save(out / "musculo-original.png")
    mus_g2.save(out / "musculo-g2.png")
    diff_image(mus_orig, mus_g2).save(out / "musculo-diff.png")

    metrics = {
        "schema": "srstudio/g2-meat-strip-visual-cert/1",
        "source_sha": checked,
        "pptx": {"name": pptx.name, "sha256": actual_pptx_sha, "slide_emu": [slide_w, slide_h], "reference_renderer": "LibreOffice headless -> PDF -> pypdfium2"},
        "structure": {"meat_strip_roots": 1, "product_cells": 4},
        "font": font_payload,
        "musculo_fill_rect": actual_fill,
        "line_spacing": {"status": "NOT VERIFIED", "reason": "No reliable glyph-baseline segmentation is available in this harness; raster region deltas are recorded instead."},
        "letter_spacing": {"status": "NOT VERIFIED", "reason": "Raster text-region deltas are recorded, but a glyph-advance-only metric cannot be isolated reliably."},
        "regions": {},
        "visual_differences": [],
    }

    for profile_id, slot in zip(PROFILE_ORDER, slots):
        profile = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
        source_root = profile["root_emu"]
        role_map = {
            "IMAGE": ["image"],
            "NAME": ["name"],
            "PRICE": ["currency", "integer", "decimal"],
            "UNIT": ["unit"],
        }
        for region_name, role_keys in role_map.items():
            source_rects = [relative_rect(source_root, profile["roles"][key]["relative"]) for key in role_keys]
            src_rect = source_rects[0]
            for other in source_rects[1:]: src_rect = union_two(src_rect, other)
            binding_by_key = {"image": BindingRole.IMAGE, "name": BindingRole.NAME, "currency": BindingRole.CURRENCY, "integer": BindingRole.PRICE_REAIS, "decimal": BindingRole.PRICE_CENTS, "unit": BindingRole.UNIT}
            runtime_rects = []
            for key in role_keys:
                node = session.page.node(slot.node_by_role[binding_by_key[key].value])
                rect = node.rect.normalized(); runtime_rects.append((rect.x, rect.y, rect.width, rect.height))
            run_rect = runtime_rects[0]
            for other in runtime_rects[1:]: run_rect = union_two(run_rect, other)
            ref_region = crop_from_logical(original_full, src_rect, slide_w, slide_h)
            g2_region = crop_from_logical(g2_full, run_rect, session.page.width, session.page.height)
            key = f"{profile_id.upper()} {region_name}"
            metrics["regions"][key] = pixel_metrics(ref_region, g2_region)

    # Shared visual diagnostics. CURVE intentionally focuses on the two curved end zones.
    metrics["regions"]["BACKGROUND"] = pixel_metrics(original, candidate)
    source_wine = (185365.0, 9628281.0, 5706903.0 - 185365.0, 306437.0)
    runtime_wine = None
    shared_nodes = [session.page.node(n) for n in snapshot.get("shared_visual_nodes") or []]
    shared_nodes = [n for n in shared_nodes if n is not None]
    path_node = next((n for n in shared_nodes if str(n.metadata.get("source_shape_id") or "") == "3"), None)
    if path_node is not None:
        r = path_node.rect.normalized(); runtime_wine = (r.x, r.y, r.width, r.height)
        wine_ref = crop_from_logical(original_full, source_wine, slide_w, slide_h)
        wine_g2 = crop_from_logical(g2_full, runtime_wine, session.page.width, session.page.height)
        metrics["regions"]["WINE STRIP"] = pixel_metrics(wine_ref, wine_g2)
        # First/last 8% of the strip captures the custGeom curves without pretending to isolate every antialiased edge pixel.
        for label, xfrac in (("CURVE LEFT", 0.0), ("CURVE RIGHT", 0.92)):
            src_curve = (source_wine[0] + source_wine[2] * xfrac, source_wine[1], source_wine[2] * 0.08, source_wine[3])
            run_curve = (runtime_wine[0] + runtime_wine[2] * xfrac, runtime_wine[1], runtime_wine[2] * 0.08, runtime_wine[3])
            metrics["regions"][label] = pixel_metrics(crop_from_logical(original_full, src_curve, slide_w, slide_h), crop_from_logical(g2_full, run_curve, session.page.width, session.page.height))
        metrics["regions"]["CURVE"] = {"left": metrics["regions"]["CURVE LEFT"], "right": metrics["regions"]["CURVE RIGHT"]}

    for index, profile_id in enumerate(PROFILE_ORDER[:3], start=1):
        profile = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
        root = profile["root_emu"]
        source_sep = (float(root[0] + root[2]) - 19050.0, 8736104.0, 38100.0, 790533.0)
        sep_source_id = str(profile["separator_source_id"])
        sep_node = next((n for n in shared_nodes if str(n.metadata.get("source_shape_id") or "") == sep_source_id), None)
        if sep_node is not None:
            rr = sep_node.rect.normalized(); runtime_sep = (rr.x - max(1.0, rr.width), rr.y, max(2.0, rr.width * 2.0), rr.height)
            metrics["regions"][f"SEPARATOR {index}"] = pixel_metrics(crop_from_logical(original_full, source_sep, slide_w, slide_h), crop_from_logical(g2_full, runtime_sep, session.page.width, session.page.height))

    metrics["regions"]["MUSCULO IMAGE RASTER"] = pixel_metrics(mus_orig, mus_g2)
    for key, value in metrics["regions"].items():
        if not isinstance(value, dict) or "changed_ratio" not in value:
            continue
        if float(value["changed_ratio"]) > 0:
            metrics["visual_differences"].append({
                "region": key,
                "EXPECTED": "PPTX ground-truth raster",
                "ACTUAL": "Qt/G2 candidate raster",
                "DELTA": value,
                "SEVERITY": severity(float(value["changed_ratio"])),
                "LIKELY_ROOT_CAUSE": "Requires visual inspection; possible font fallback, text metrics, antialiasing, image fill/crop, or shape rasterization difference.",
            })

    (out / "meat-strip-visual-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    required = [
        "meat-strip-original.png", "meat-strip-g2.png", "meat-strip-original-vs-g2.png", "meat-strip-diff.png",
        "musculo-original.png", "musculo-g2.png", "musculo-diff.png",
        "meat-strip-visual-metrics.json", "meat-strip-font-resolution.json",
    ]
    missing = [name for name in required if not (out / name).is_file() or (out / name).stat().st_size <= 0]
    if missing:
        raise RuntimeError(f"Required artifacts missing: {missing}")
    if run_git(source_root, "status", "--porcelain") or subprocess.call(["git", "-C", str(source_root), "diff", "--quiet"]) != 0:
        raise RuntimeError("Frozen source checkout changed during certification")
    print("CERTIFICATION_EVIDENCE_READY=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
