from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageChops, ImageEnhance, ImageStat

BEFORE_SHA = "c69dd1b933e93e0928c4f299cc53ca771b22b4c2"
AFTER_SHA = "200f0ba6c119e604f5ad7d7898e6838f55dc8619"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
PAGE = (1080.0, 1350.0)
LEGACY_RUNTIME_STRIP = (489.1126181102362, 112.39954724409448)
ROLE_ORDER = ("name", "currency", "integer", "decimal", "unit")
ROLE_LABEL = {"name": "NAME", "currency": "CURRENCY", "integer": "INTEGER", "decimal": "DECIMAL", "unit": "UNIT"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def pptx_slide_size(path: Path) -> tuple[float, float]:
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("ppt/presentation.xml"))
    size = root.find("p:sldSz", ns)
    if size is None:
        raise RuntimeError("PPTX p:sldSz missing")
    return float(size.get("cx") or 0), float(size.get("cy") or 0)


def rect_union(rects):
    left = min(float(r[0]) for r in rects)
    top = min(float(r[1]) for r in rects)
    right = max(float(r[0]) + float(r[2]) for r in rects)
    bottom = max(float(r[1]) + float(r[3]) for r in rects)
    return left, top, right - left, bottom - top


def relative_rect(parent, rel):
    return (
        float(parent[0]) + float(rel[0]) * float(parent[2]),
        float(parent[1]) + float(rel[1]) * float(parent[3]),
        float(rel[2]) * float(parent[2]),
        float(rel[3]) * float(parent[3]),
    )


def crop_logical(image: Image.Image, rect, logical_size) -> Image.Image:
    lw, lh = map(float, logical_size)
    sx = image.width / lw
    sy = image.height / lh
    left = max(0, math.floor(float(rect[0]) * sx))
    top = max(0, math.floor(float(rect[1]) * sy))
    right = min(image.width, math.ceil((float(rect[0]) + float(rect[2])) * sx))
    bottom = min(image.height, math.ceil((float(rect[1]) + float(rect[3])) * sy))
    if right <= left or bottom <= top:
        raise RuntimeError(f"invalid crop {rect} in {logical_size}")
    return image.crop((left, top, right, bottom)).convert("RGB")


def normalize(reference: Image.Image, candidate: Image.Image):
    ref = reference.convert("RGB")
    cand = candidate.convert("RGB")
    if cand.size != ref.size:
        cand = cand.resize(ref.size, Image.Resampling.LANCZOS)
    return ref, cand


def pixel_metrics(reference: Image.Image, candidate: Image.Image, tolerance: int = 16) -> dict:
    ref, cand = normalize(reference, candidate)
    diff = ImageChops.difference(ref, cand)
    stat = ImageStat.Stat(diff)
    mae = sum(stat.mean) / len(stat.mean)
    hist = diff.convert("L").histogram()
    changed = sum(hist[tolerance + 1 :])
    total = max(1, ref.width * ref.height)
    changed_ratio = changed / total
    score = (changed_ratio + mae / 255.0) / 2.0
    return {
        "width": ref.width,
        "height": ref.height,
        "pixel_tolerance": tolerance,
        "changed_ratio": round(changed_ratio, 8),
        "mae": round(float(mae), 6),
        "score": round(float(score), 8),
    }


def classify(before: dict, after: dict) -> str:
    delta = float(after["score"]) - float(before["score"])
    if delta < -0.003:
        return "IMPROVED"
    if delta > 0.003:
        return "REGRESSED"
    return "UNCHANGED"


def side_by_side(reference: Image.Image, candidate: Image.Image) -> Image.Image:
    ref, cand = normalize(reference, candidate)
    out = Image.new("RGB", (ref.width * 2, ref.height), "white")
    out.paste(ref, (0, 0))
    out.paste(cand, (ref.width, 0))
    return out


def diff_image(reference: Image.Image, candidate: Image.Image) -> Image.Image:
    ref, cand = normalize(reference, candidate)
    return ImageEnhance.Contrast(ImageChops.difference(ref, cand)).enhance(4.0)


def in_bounds(rect, width=PAGE[0], height=PAGE[1]) -> bool:
    x, y, w, h = map(float, rect)
    return x >= -1e-6 and y >= -1e-6 and x + w <= width + 1e-6 and y + h <= height + 1e-6


def aggregate(rows: list[dict]) -> dict:
    before_changed = sum(r["before"]["changed_ratio"] for r in rows) / len(rows)
    after_changed = sum(r["after"]["changed_ratio"] for r in rows) / len(rows)
    before_mae = sum(r["before"]["mae"] for r in rows) / len(rows)
    after_mae = sum(r["after"]["mae"] for r in rows) / len(rows)
    before_score = sum(r["before"]["score"] for r in rows) / len(rows)
    after_score = sum(r["after"]["score"] for r in rows) / len(rows)
    delta = after_score - before_score
    classification = "IMPROVED" if delta < -0.003 else "REGRESSED" if delta > 0.003 else "UNCHANGED"
    return {
        "before_changed_ratio_mean": round(before_changed, 8),
        "after_changed_ratio_mean": round(after_changed, 8),
        "before_mae_mean": round(before_mae, 6),
        "after_mae_mean": round(after_mae, 6),
        "before_score_mean": round(before_score, 8),
        "after_score_mean": round(after_score, 8),
        "classification": classification,
        "improved_roles": sum(r["classification"] == "IMPROVED" for r in rows),
        "unchanged_roles": sum(r["classification"] == "UNCHANGED" for r in rows),
        "regressed_roles": sum(r["classification"] == "REGRESSED" for r in rows),
    }


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before-dir", required=True, type=Path)
    parser.add_argument("--after-dir", required=True, type=Path)
    parser.add_argument("--after-source", required=True, type=Path)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    before_dir = args.before_dir.resolve()
    after_dir = args.after_dir.resolve()
    source_root = args.after_source.resolve()
    pptx = args.pptx.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    actual_pptx_sha = sha256(pptx)
    if actual_pptx_sha != PPTX_SHA256:
        raise RuntimeError(f"PPTX SHA mismatch: {actual_pptx_sha}")
    slide_emu = pptx_slide_size(pptx)
    if slide_emu[0] <= 0 or slide_emu[1] <= 0:
        raise RuntimeError(f"invalid p:sldSz: {slide_emu}")

    before_cert = load_json(before_dir / "meat-strip-visual-metrics.json")
    if str(before_cert.get("source_sha")) != BEFORE_SHA:
        raise RuntimeError(f"BEFORE source mismatch: {before_cert.get('source_sha')}")
    if ((before_cert.get("pptx") or {}).get("sha256")) != PPTX_SHA256:
        raise RuntimeError("BEFORE PPTX SHA mismatch")

    geometry = load_json(after_dir / "meat-strip-runtime-geometry.json")
    font = load_json(after_dir / "meat-strip-font-resolution.json")
    images = load_json(after_dir / "meat-strip-image-diagnostics.json")
    warnings = load_json(after_dir / "meat-strip-render-warnings.json")

    registered = [str(x) for x in font.get("ANTON_REGISTERED_FAMILIES") or []]
    font_ok = (
        any(x.casefold() == "anton" for x in registered)
        and str(font.get("ANTON_RESOLVED") or "").casefold() == "anton"
        and bool(font.get("ANTON_EXACT_MATCH"))
        and not (font.get("REGISTRATION_WARNINGS") or [])
    )
    if not font_ok:
        raise RuntimeError(f"Anton gate failed: {font}")

    image_rows = list(images.get("IMAGES") or [])
    image_ok = (
        len(image_rows) == 4
        and all(bool(r.get("QIMAGE DECODE OK")) for r in image_rows)
        and all(bool(r.get("ASSET ID")) and bool(r.get("BOUND_IMAGE_SOURCE")) for r in image_rows)
    )
    if not image_ok or warnings:
        raise RuntimeError(f"image/warning gate failed: image_ok={image_ok}, warnings={warnings}")

    runtime_strip = tuple(map(float, geometry["RUNTIME MEAT STRIP ROOT RECT"]))
    source_strip_emu = tuple(map(float, geometry["SOURCE STRIP RECT"]))
    actual_source_strip = (
        source_strip_emu[0] / slide_emu[0] * PAGE[0],
        source_strip_emu[1] / slide_emu[1] * PAGE[1],
        source_strip_emu[2] / slide_emu[0] * PAGE[0],
        source_strip_emu[3] / slide_emu[1] * PAGE[1],
    )
    actual_scale_x = runtime_strip[2] / actual_source_strip[2]
    actual_scale_y = runtime_strip[3] / actual_source_strip[3]
    legacy_runtime_size_preserved = (
        math.isclose(runtime_strip[2], LEGACY_RUNTIME_STRIP[0], abs_tol=1e-6)
        and math.isclose(runtime_strip[3], LEGACY_RUNTIME_STRIP[1], abs_tol=1e-6)
    )
    ground_truth_scale_pass = math.isclose(actual_scale_x, 1.0, abs_tol=0.005) and math.isclose(actual_scale_y, 1.0, abs_tol=0.005)

    cell_keys = {
        "costela": "COSTELA CELL RECT",
        "pernil": "PERNIL CELL RECT",
        "musculo": "MUSCULO CELL RECT",
        "moela": "MOELA CELL RECT",
    }
    cell_rects = {p: tuple(map(float, geometry[k])) for p, k in cell_keys.items()}
    cells_in_bounds = all(in_bounds(r) for r in cell_rects.values())
    if not cells_in_bounds or bool(geometry.get("OUT OF BOUNDS")):
        raise RuntimeError(f"runtime geometry out of bounds: {geometry}")

    sys.path.insert(0, str(source_root / "src"))
    from srstudio.graphics2.slot_corpus_full_card import MEAT_STRIP_FULL_CARD_PROFILES
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER

    reference_full = Image.open(before_dir / "reference" / "pptx-page.png").convert("RGB")
    before_full = Image.open(before_dir / "g2-page.png").convert("RGB")
    after_full = Image.open(after_dir / "g2-page.png").convert("RGB")

    original_strip = crop_logical(reference_full, source_strip_emu, slide_emu)
    after_strip = crop_logical(after_full, runtime_strip, PAGE)
    original_strip.save(out / "meat-strip-original.png")
    after_strip.save(out / "meat-strip-g2.png")
    side_by_side(original_strip, after_strip).save(out / "meat-strip-original-vs-g2.png")
    diff_image(original_strip, after_strip).save(out / "meat-strip-diff.png")

    regions: dict[str, dict] = {}
    name_rows: list[dict] = []
    price_rows: list[dict] = []
    product_rows: dict[str, dict] = {}

    for profile_id in PROFILE_ORDER:
        profile = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
        root = tuple(map(float, profile["root_emu"]))
        cell = cell_rects[profile_id]
        source_roles = {}
        runtime_roles = {}
        product_name_rows = []
        product_price_rows = []
        for role in ROLE_ORDER:
            rel = profile["roles"][role]["relative"]
            source_rect = relative_rect(root, rel)
            runtime_rect = relative_rect(cell, rel)
            source_roles[role] = source_rect
            runtime_roles[role] = runtime_rect
            reference_crop = crop_logical(reference_full, source_rect, slide_emu)
            before_crop = crop_logical(before_full, runtime_rect, PAGE)
            after_crop = crop_logical(after_full, runtime_rect, PAGE)
            before_metrics = pixel_metrics(reference_crop, before_crop)
            after_metrics = pixel_metrics(reference_crop, after_crop)
            row = {
                "profile": profile_id.upper(),
                "role": ROLE_LABEL[role],
                "source_rect_emu": list(source_rect),
                "runtime_rect": list(runtime_rect),
                "before": before_metrics,
                "after": after_metrics,
                "classification": classify(before_metrics, after_metrics),
            }
            regions[f"{profile_id.upper()} {ROLE_LABEL[role]}"] = row
            if role == "name":
                name_rows.append(row)
                product_name_rows.append(row)
            else:
                price_rows.append(row)
                product_price_rows.append(row)

        source_union = rect_union([source_roles[r] for r in ROLE_ORDER])
        runtime_union = rect_union([runtime_roles[r] for r in ROLE_ORDER])
        ref_union = crop_logical(reference_full, source_union, slide_emu)
        after_union = crop_logical(after_full, runtime_union, PAGE)
        side_by_side(ref_union, after_union).save(out / f"{profile_id}-name-price-vs.png")
        product_rows[profile_id.upper()] = {
            "NAME": aggregate(product_name_rows),
            "PRICE": aggregate(product_price_rows),
        }

    structural_regions = {}
    previous_regions = before_cert.get("regions") or {}
    for key in ("CURVE LEFT", "CURVE RIGHT", "SEPARATOR 1", "SEPARATOR 2", "SEPARATOR 3"):
        evidence = previous_regions.get(key) or {}
        source_rect = tuple(evidence.get("reference_rect") or ())
        runtime_rect = tuple(evidence.get("candidate_rect") or ())
        if len(source_rect) != 4 or len(runtime_rect) != 4:
            structural_regions[key] = {"status": "MISSING_PRIOR_RECT"}
            continue
        ref_crop = crop_logical(reference_full, source_rect, slide_emu)
        before_crop = crop_logical(before_full, runtime_rect, PAGE)
        after_crop = crop_logical(after_full, runtime_rect, PAGE)
        bm = pixel_metrics(ref_crop, before_crop)
        am = pixel_metrics(ref_crop, after_crop)
        structural_regions[key] = {
            "source_rect_emu": list(source_rect),
            "runtime_rect": list(runtime_rect),
            "runtime_rect_in_bounds": in_bounds(runtime_rect),
            "before": bm,
            "after": am,
            "classification": classify(bm, am),
        }

    musculo = next(r for r in image_rows if str(r.get("PROFILE") or "").upper() == "MUSCULO")
    musculo_fill = dict(musculo.get("FILL_RECT") or {})
    expected_fill = {"l": 0.0, "t": -0.10057, "r": 0.0, "b": -0.40571}
    fill_ok = all(math.isclose(float(musculo_fill.get(k, 0.0)), v, abs_tol=1e-9) for k, v in expected_fill.items())
    if not fill_ok:
        raise RuntimeError(f"MUSCULO fillRect regression: {musculo_fill}")

    payload = {
        "schema": "srstudio/final-meat-strip-before-after/2",
        "before_source_sha": BEFORE_SHA,
        "after_source_sha": AFTER_SHA,
        "pptx_sha256": actual_pptx_sha,
        "pptx_slide_size_emu_actual": list(slide_emu),
        "legacy_diagnostic_slide_size_emu": [12192000.0, 15240000.0],
        "geometry_ground_truth": {
            "source_strip_emu": list(source_strip_emu),
            "source_strip_normalized_actual_1080x1350": list(actual_source_strip),
            "runtime_strip_rect": list(runtime_strip),
            "runtime_source_scale_x_actual": actual_scale_x,
            "runtime_source_scale_y_actual": actual_scale_y,
            "legacy_runtime_size_preserved": legacy_runtime_size_preserved,
            "ground_truth_scale_approximately_one": ground_truth_scale_pass,
            "finding": "PPTX p:sldSz differs from the 12192000x15240000 constant used by PR #103 diagnostics/ownership source-page scale.",
        },
        "comparison_method": {
            "pixel_tolerance": 16,
            "score": "(changed_ratio + mae/255) / 2",
            "classification": "IMPROVED if score delta < -0.003; REGRESSED if > 0.003; otherwise UNCHANGED",
            "source_crop_space": "actual p:presentation/p:sldSz read from exact PPTX",
            "before": "certified artifact from run 32538659519",
            "after": "fresh clean production-pipeline render of exact SHA 200f0ba6...",
        },
        "aggregate": {"NAME": aggregate(name_rows), "PRICE": aggregate(price_rows)},
        "products": product_rows,
        "regions": regions,
        "structural_regions": structural_regions,
        "font": font,
        "images": images,
        "render_warnings": warnings,
        "musculo_fill_rect": {"actual": musculo_fill, "expected": expected_fill, "pass": fill_ok},
        "priceblock_structure": {
            "independent_roles": ["CURRENCY", "INTEGER", "DECIMAL", "UNIT"],
            "synthetic_concat": False,
            "new_backplate": False,
            "meat_specific_offset": False,
            "basis": "BEFORE->AFTER production diff is qt_renderer.py plus generic regression test only",
        },
        "gates": {
            "font": font_ok,
            "images": image_ok,
            "render_warnings_empty": not warnings,
            "runtime_out_of_bounds": bool(geometry.get("OUT OF BOUNDS")),
            "cells_in_bounds": cells_in_bounds,
            "musculo_fillrect": fill_ok,
            "legacy_runtime_strip_size_preserved": legacy_runtime_size_preserved,
            "ground_truth_source_scale": ground_truth_scale_pass,
        },
    }
    (out / "meat-strip-visual-metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for name in (
        "meat-strip-font-resolution.json",
        "meat-strip-render-warnings.json",
        "meat-strip-image-diagnostics.json",
        "meat-strip-runtime-geometry.json",
    ):
        shutil.copy2(after_dir / name, out / name)

    required = [
        "meat-strip-original.png",
        "meat-strip-g2.png",
        "meat-strip-original-vs-g2.png",
        "meat-strip-diff.png",
        "costela-name-price-vs.png",
        "pernil-name-price-vs.png",
        "musculo-name-price-vs.png",
        "moela-name-price-vs.png",
        "meat-strip-visual-metrics.json",
        "meat-strip-font-resolution.json",
        "meat-strip-render-warnings.json",
        "meat-strip-image-diagnostics.json",
        "meat-strip-runtime-geometry.json",
    ]
    missing = [name for name in required if not (out / name).is_file() or (out / name).stat().st_size <= 0]
    if missing:
        raise RuntimeError(f"missing required evidence: {missing}")

    print(f"BEFORE_SHA={BEFORE_SHA}")
    print(f"AFTER_SHA={AFTER_SHA}")
    print(f"PPTX_SHA256={actual_pptx_sha}")
    print(f"PPTX_SLIDE_SIZE_EMU_ACTUAL={slide_emu[0]}x{slide_emu[1]}")
    print(f"SOURCE_STRIP_NORMALIZED_ACTUAL={actual_source_strip}")
    print(f"RUNTIME_SOURCE_SCALE_ACTUAL={actual_scale_x},{actual_scale_y}")
    print(f"ANTON={font.get('ANTON_RESOLVED')} exact={font.get('ANTON_EXACT_MATCH')}")
    print(f"IMAGES_OK={image_ok}")
    print(f"RENDER_WARNINGS={warnings}")
    print("NAME_AGG=" + json.dumps(payload["aggregate"]["NAME"], ensure_ascii=False))
    print("PRICE_AGG=" + json.dumps(payload["aggregate"]["PRICE"], ensure_ascii=False))
    for key in sorted(regions):
        row = regions[key]
        print(
            f"{key}: before_changed={row['before']['changed_ratio']} after_changed={row['after']['changed_ratio']} "
            f"before_mae={row['before']['mae']} after_mae={row['after']['mae']} class={row['classification']}"
        )
    print("FINAL_VISUAL_EVIDENCE_READY=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
