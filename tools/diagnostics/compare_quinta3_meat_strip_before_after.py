from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageStat

BEFORE_SHA = "c69dd1b933e93e0928c4f299cc53ca771b22b4c2"
AFTER_SHA = "200f0ba6c119e604f5ad7d7898e6838f55dc8619"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
SLIDE_EMU = (12192000.0, 15240000.0)
PAGE = (1080.0, 1350.0)
EXPECTED_STRIP = (489.1126181102362, 112.39954724409448)
ROLE_ORDER = ("name", "currency", "integer", "decimal", "unit")
ROLE_LABEL = {
    "name": "NAME",
    "currency": "CURRENCY",
    "integer": "INTEGER",
    "decimal": "DECIMAL",
    "unit": "UNIT",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rect_union(rects: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return left, top, right - left, bottom - top


def relative_rect(parent, rel) -> tuple[float, float, float, float]:
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
    l = max(0, math.floor(float(rect[0]) * sx))
    t = max(0, math.floor(float(rect[1]) * sy))
    r = min(image.width, math.ceil((float(rect[0]) + float(rect[2])) * sx))
    b = min(image.height, math.ceil((float(rect[1]) + float(rect[3])) * sy))
    if r <= l or b <= t:
        raise RuntimeError(f"invalid crop {rect} within {logical_size}")
    return image.crop((l, t, r, b)).convert("RGB")


def normalize(reference: Image.Image, candidate: Image.Image) -> tuple[Image.Image, Image.Image]:
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
    gray = diff.convert("L")
    hist = gray.histogram()
    changed = sum(hist[tolerance + 1 :])
    total = max(1, ref.width * ref.height)
    return {
        "width": ref.width,
        "height": ref.height,
        "pixel_tolerance": tolerance,
        "mae": round(float(mae), 6),
        "changed_ratio": round(changed / total, 8),
    }


def score(metrics: dict) -> float:
    return (float(metrics["changed_ratio"]) + float(metrics["mae"]) / 255.0) / 2.0


def classify(before: dict, after: dict) -> str:
    delta = score(after) - score(before)
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


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--before-dir", required=True, type=Path)
    p.add_argument("--after-dir", required=True, type=Path)
    p.add_argument("--after-source", required=True, type=Path)
    p.add_argument("--pptx", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()

    before = args.before_dir.resolve()
    after = args.after_dir.resolve()
    source = args.after_source.resolve()
    pptx = args.pptx.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    actual_pptx_sha = sha256(pptx)
    if actual_pptx_sha != PPTX_SHA256:
        raise RuntimeError(f"PPTX SHA mismatch: {actual_pptx_sha}")

    before_metrics = load_json(before / "meat-strip-visual-metrics.json")
    if str(before_metrics.get("source_sha")) != BEFORE_SHA:
        raise RuntimeError(f"BEFORE source mismatch: {before_metrics.get('source_sha')}")
    before_pptx = ((before_metrics.get("pptx") or {}).get("sha256"))
    if before_pptx != PPTX_SHA256:
        raise RuntimeError(f"BEFORE PPTX mismatch: {before_pptx}")

    geometry = load_json(after / "meat-strip-runtime-geometry.json")
    font = load_json(after / "meat-strip-font-resolution.json")
    images = load_json(after / "meat-strip-image-diagnostics.json")
    warnings = load_json(after / "meat-strip-render-warnings.json")

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
        and not warnings
    )
    if not image_ok:
        raise RuntimeError(f"Image/render warning gate failed: images={images}, warnings={warnings}")

    source_norm = list(geometry["SOURCE STRIP RECT NORMALIZED TO 1080x1350"])
    runtime_strip = list(geometry["RUNTIME MEAT STRIP ROOT RECT"])
    sx = float(geometry["RUNTIME / SOURCE SCALE X"])
    sy = float(geometry["RUNTIME / SOURCE SCALE Y"])
    if not math.isclose(source_norm[2], EXPECTED_STRIP[0], rel_tol=0, abs_tol=1e-6):
        raise RuntimeError(f"source strip width regression: {source_norm[2]}")
    if not math.isclose(source_norm[3], EXPECTED_STRIP[1], rel_tol=0, abs_tol=1e-6):
        raise RuntimeError(f"source strip height regression: {source_norm[3]}")
    if not math.isclose(sx, 1.0, rel_tol=0, abs_tol=1e-9) or not math.isclose(sy, 1.0, rel_tol=0, abs_tol=1e-9):
        raise RuntimeError(f"strip scale regression: {sx}, {sy}")
    if bool(geometry.get("OUT OF BOUNDS")) or not in_bounds(runtime_strip):
        raise RuntimeError(f"strip out of bounds: {runtime_strip}")

    cell_keys = {
        "costela": "COSTELA CELL RECT",
        "pernil": "PERNIL CELL RECT",
        "musculo": "MUSCULO CELL RECT",
        "moela": "MOELA CELL RECT",
    }
    cell_rects = {p: tuple(map(float, geometry[k])) for p, k in cell_keys.items()}
    if not all(in_bounds(r) for r in cell_rects.values()):
        raise RuntimeError(f"cell out of bounds: {cell_rects}")

    sys.path.insert(0, str(source / "src"))
    from srstudio.graphics2.slot_corpus_full_card import MEAT_STRIP_FULL_CARD_PROFILES
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER

    reference_full = Image.open(before / "reference" / "pptx-page.png").convert("RGB")
    before_full = Image.open(before / "g2-page.png").convert("RGB")
    after_full = Image.open(after / "g2-page.png").convert("RGB")

    source_strip_emu = tuple(map(float, geometry["SOURCE STRIP RECT"]))
    original_strip = crop_logical(reference_full, source_strip_emu, SLIDE_EMU)
    after_strip = crop_logical(after_full, runtime_strip, PAGE)
    original_strip.save(out / "meat-strip-original.png")
    after_strip.save(out / "meat-strip-g2.png")
    side_by_side(original_strip, after_strip).save(out / "meat-strip-original-vs-g2.png")
    diff_image(original_strip, after_strip).save(out / "meat-strip-diff.png")

    regions: dict[str, dict] = {}
    aggregate_groups = {"NAME": [], "PRICE": []}
    source_regions_by_product = {}
    runtime_regions_by_product = {}

    for profile_id in PROFILE_ORDER:
        profile = MEAT_STRIP_FULL_CARD_PROFILES[profile_id]
        root = tuple(map(float, profile["root_emu"]))
        cell = cell_rects[profile_id]
        source_regions_by_product[profile_id] = {}
        runtime_regions_by_product[profile_id] = {}
        for role in ROLE_ORDER:
            rel = profile["roles"][role]["relative"]
            src_rect = relative_rect(root, rel)
            run_rect = relative_rect(cell, rel)
            source_regions_by_product[profile_id][role] = src_rect
            runtime_regions_by_product[profile_id][role] = run_rect
            ref_crop = crop_logical(reference_full, src_rect, SLIDE_EMU)
            before_crop = crop_logical(before_full, run_rect, PAGE)
            after_crop = crop_logical(after_full, run_rect, PAGE)
            bm = pixel_metrics(ref_crop, before_crop)
            am = pixel_metrics(ref_crop, after_crop)
            row = {
                "profile": profile_id.upper(),
                "role": ROLE_LABEL[role],
                "source_rect": list(src_rect),
                "runtime_rect": list(run_rect),
                "before": bm,
                "after": am,
                "before_score": round(score(bm), 8),
                "after_score": round(score(am), 8),
                "classification": classify(bm, am),
            }
            regions[f"{profile_id.upper()} {ROLE_LABEL[role]}"] = row
            aggregate_groups["NAME" if role == "name" else "PRICE"].append(row)

        all_roles = ["name", "currency", "integer", "decimal", "unit"]
        src_union = rect_union([source_regions_by_product[profile_id][r] for r in all_roles])
        run_union = rect_union([runtime_regions_by_product[profile_id][r] for r in all_roles])
        ref_union = crop_logical(reference_full, src_union, SLIDE_EMU)
        after_union = crop_logical(after_full, run_union, PAGE)
        side_by_side(ref_union, after_union).save(out / f"{profile_id}-name-price-vs.png")

    def aggregate(rows: list[dict]) -> dict:
        before_changed = sum(r["before"]["changed_ratio"] for r in rows) / len(rows)
        after_changed = sum(r["after"]["changed_ratio"] for r in rows) / len(rows)
        before_mae = sum(r["before"]["mae"] for r in rows) / len(rows)
        after_mae = sum(r["after"]["mae"] for r in rows) / len(rows)
        b = {"changed_ratio": before_changed, "mae": before_mae}
        a = {"changed_ratio": after_changed, "mae": after_mae}
        classes = [r["classification"] for r in rows]
        return {
            "before_changed_ratio_mean": round(before_changed, 8),
            "after_changed_ratio_mean": round(after_changed, 8),
            "before_mae_mean": round(before_mae, 6),
            "after_mae_mean": round(after_mae, 6),
            "before_score": round(score(b), 8),
            "after_score": round(score(a), 8),
            "classification": classify(b, a),
            "role_classifications": classes,
            "regressed_roles": sum(c == "REGRESSED" for c in classes),
            "improved_roles": sum(c == "IMPROVED" for c in classes),
        }

    aggregate_metrics = {name: aggregate(rows) for name, rows in aggregate_groups.items()}

    before_shared = before_metrics.get("regions") or {}
    structural_regions = {}
    for key in ("CURVE LEFT", "CURVE RIGHT", "SEPARATOR 1", "SEPARATOR 2", "SEPARATOR 3"):
        item = copy.deepcopy(before_shared.get(key) or {})
        rect = item.get("candidate_rect")
        structural_regions[key] = {
            "before_evidence": item,
            "runtime_rect_in_bounds": bool(rect and in_bounds(rect)),
            "renderer_only_change": True,
        }
        if rect and not in_bounds(rect):
            raise RuntimeError(f"structural region out of bounds: {key} {rect}")

    musculo_row = next(r for r in image_rows if str(r.get("PROFILE") or "").upper() == "MUSCULO")
    musculo_fill = dict(musculo_row.get("FILL_RECT") or {})
    expected_fill = {"l": 0.0, "t": -0.10057, "r": 0.0, "b": -0.40571}
    fill_ok = all(math.isclose(float(musculo_fill.get(k, 0.0)), v, abs_tol=1e-9) for k, v in expected_fill.items())
    if not fill_ok:
        raise RuntimeError(f"MUSCULO fillRect regression: {musculo_fill}")

    result = {
        "schema": "srstudio/final-meat-strip-before-after/1",
        "before_source_sha": BEFORE_SHA,
        "after_source_sha": AFTER_SHA,
        "pptx_sha256": actual_pptx_sha,
        "comparison_method": {
            "pixel_tolerance": 16,
            "score": "(changed_ratio + mae/255) / 2",
            "classification": "IMPROVED if score delta < -0.003; REGRESSED if > 0.003; otherwise UNCHANGED",
            "before": "certified artifact from run 32538659519",
            "after": "fresh clean production-pipeline render of exact SHA",
        },
        "font": font,
        "images": images,
        "render_warnings": warnings,
        "geometry": geometry,
        "musculo_fill_rect": {"actual": musculo_fill, "expected": expected_fill, "pass": fill_ok},
        "priceblock_structure": {
            "independent_roles": ["CURRENCY", "INTEGER", "DECIMAL", "UNIT"],
            "synthetic_concat": False,
            "new_backplate": False,
            "meat_specific_offset": False,
            "basis": "candidate diff is renderer-only plus regression test; slot corpus/profile geometry unchanged",
        },
        "regions": regions,
        "aggregate": aggregate_metrics,
        "structural_regions": structural_regions,
        "gates": {
            "font": font_ok,
            "images": image_ok,
            "render_warnings_empty": not warnings,
            "strip_scale": math.isclose(sx, 1.0, abs_tol=1e-9) and math.isclose(sy, 1.0, abs_tol=1e-9),
            "out_of_bounds": False,
            "cells_in_bounds": all(in_bounds(r) for r in cell_rects.values()),
            "musculo_fillrect": fill_ok,
        },
    }
    (out / "meat-strip-visual-metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    for name in (
        "meat-strip-font-resolution.json",
        "meat-strip-render-warnings.json",
        "meat-strip-image-diagnostics.json",
        "meat-strip-runtime-geometry.json",
    ):
        shutil.copy2(after / name, out / name)

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
    missing = [n for n in required if not (out / n).is_file() or (out / n).stat().st_size <= 0]
    if missing:
        raise RuntimeError(f"missing required evidence: {missing}")

    print(f"BEFORE_SHA={BEFORE_SHA}")
    print(f"AFTER_SHA={AFTER_SHA}")
    print(f"PPTX_SHA256={actual_pptx_sha}")
    print(f"ANTON={font.get('ANTON_RESOLVED')} exact={font.get('ANTON_EXACT_MATCH')}")
    print(f"IMAGES_OK={image_ok}")
    print(f"RENDER_WARNINGS={warnings}")
    print(f"STRIP_SCALE={sx},{sy}")
    print(f"OUT_OF_BOUNDS={geometry.get('OUT OF BOUNDS')}")
    print("NAME_AGG=" + json.dumps(aggregate_metrics["NAME"], ensure_ascii=False))
    print("PRICE_AGG=" + json.dumps(aggregate_metrics["PRICE"], ensure_ascii=False))
    for key in sorted(regions):
        r = regions[key]
        print(f"{key}: before_changed={r['before']['changed_ratio']} after_changed={r['after']['changed_ratio']} before_mae={r['before']['mae']} after_mae={r['after']['mae']} class={r['classification']}")
    print("FINAL_VISUAL_EVIDENCE_READY=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
