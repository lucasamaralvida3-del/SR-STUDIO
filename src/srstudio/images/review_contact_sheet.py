from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from srstudio.images.association import normalize_product_name
from srstudio.images.product_priority import ProductPriorityRow, scan_product_priority
from srstudio.images.quality import asset_quality_score
from srstudio.images.safe_library import SafeImageLibrary


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    image_id: str
    product_name: str
    review_status: str
    association_status: str
    confidence: float
    quality_score: float
    preferred: bool
    path: str
    source: str


@dataclass(frozen=True, slots=True)
class ReviewGroup:
    product_name: str
    normalized_name: str
    priority_score: float
    occurrence_count: int
    source_count: int
    candidates: tuple[ReviewCandidate, ...]


def build_review_dataset(
    library,
    *,
    priority_rows: Iterable[ProductPriorityRow | dict] = (),
    max_products: int = 60,
    candidates_per_product: int = 4,
) -> tuple[ReviewGroup, ...]:
    """Build a small impact-first review queue from metadata only."""
    priority = _priority_map(priority_rows)
    grouped: dict[str, list] = {}
    display_names: dict[str, str] = {}
    for asset in library.all():
        metadata = dict(getattr(asset, "metadata", {}) or {})
        association_status = str(metadata.get("association_status", "") or "").lower()
        kind = str(getattr(asset, "kind", "") or "").lower()
        status = str(getattr(asset, "review_status", "") or "").lower()
        if status in {"rejected", "reject"} or kind == "decorative" or association_status == "decorative":
            continue
        display = str(getattr(asset, "product_name", "") or getattr(asset, "product_key", "") or "").strip()
        normalized = normalize_product_name(display)
        if not normalized:
            continue
        grouped.setdefault(normalized, []).append(asset)
        display_names.setdefault(normalized, display)

    groups: list[ReviewGroup] = []
    for normalized, assets in grouped.items():
        # A review sheet is useful only when something is pending/ambiguous or when
        # multiple valid variants exist and a preferred choice is still absent.
        pending = [asset for asset in assets if str(getattr(asset, "review_status", "") or "").lower() != "accepted"]
        has_preferred = any(bool(getattr(asset, "preferred", False)) for asset in assets)
        if not pending and (len(assets) < 2 or has_preferred):
            continue

        row = priority.get(normalized, {})
        candidates = sorted(
            (_candidate(asset) for asset in assets),
            key=lambda candidate: (
                candidate.review_status != "accepted",
                candidate.preferred,
                candidate.confidence,
                candidate.quality_score,
            ),
            reverse=True,
        )[: max(1, int(candidates_per_product))]
        groups.append(
            ReviewGroup(
                product_name=display_names[normalized],
                normalized_name=normalized,
                priority_score=float(row.get("priority_score", 0.0) or 0.0),
                occurrence_count=int(row.get("occurrence_count", 0) or 0),
                source_count=int(row.get("source_count", 0) or 0),
                candidates=tuple(candidates),
            )
        )

    groups.sort(
        key=lambda group: (
            group.priority_score,
            group.occurrence_count,
            group.source_count,
            max((candidate.confidence for candidate in group.candidates), default=0.0),
            len(group.candidates),
        ),
        reverse=True,
    )
    return tuple(groups[: max(0, int(max_products))])


def render_contact_sheet(
    groups: Iterable[ReviewGroup],
    output_path: str | Path,
    *,
    thumb_size: tuple[int, int] = (240, 240),
    candidates_per_row: int = 4,
) -> Path:
    """Render review thumbnails lazily; at most one candidate image is open at once."""
    rows = list(groups)
    thumb_w, thumb_h = thumb_size
    columns = max(1, int(candidates_per_row))
    margin = 18
    header_h = 64
    label_h = 58
    group_h = header_h + thumb_h + label_h + margin
    width = margin * 2 + columns * (thumb_w + margin)
    height = max(1, margin + len(rows) * group_h)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    y = margin
    for group_index, group in enumerate(rows, start=1):
        title = (
            f"{group_index:02d}. {group.product_name} | prioridade {group.priority_score:.2f} | "
            f"freq {group.occurrence_count} | fontes {group.source_count}"
        )
        draw.text((margin, y), title, fill="black", font=font)
        candidate_y = y + header_h
        for index, candidate in enumerate(group.candidates[:columns]):
            x = margin + index * (thumb_w + margin)
            tile = _load_thumbnail(candidate.path, thumb_size)
            canvas.paste(tile, (x, candidate_y))
            label = (
                f"{chr(65 + index)} {candidate.review_status}/{candidate.association_status or '-'} "
                f"conf={candidate.confidence:.3f} q={candidate.quality_score:.3f}"
            )
            draw.multiline_text((x, candidate_y + thumb_h + 4), label, fill="black", font=font, spacing=2)
        y += group_h

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp.png")
    canvas.save(temporary, format="PNG")
    temporary.replace(target)
    return target


def dataset_payload(groups: Iterable[ReviewGroup]) -> dict:
    rows = list(groups)
    return {
        "products": len(rows),
        "candidates": sum(len(group.candidates) for group in rows),
        "groups": [asdict(group) for group in rows],
    }


def write_dataset(path: str | Path, groups: Iterable[ReviewGroup]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(dataset_payload(groups), ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(temporary.read_text(encoding="utf-8"))
    temporary.replace(target)
    return target


def _candidate(asset) -> ReviewCandidate:
    metadata = dict(getattr(asset, "metadata", {}) or {})
    return ReviewCandidate(
        image_id=str(getattr(asset, "id", "")),
        product_name=str(getattr(asset, "product_name", "") or getattr(asset, "product_key", "") or ""),
        review_status=str(getattr(asset, "review_status", "") or ""),
        association_status=str(metadata.get("association_status", "") or ""),
        confidence=float(getattr(asset, "confidence", 0.0) or 0.0),
        quality_score=asset_quality_score(asset),
        preferred=bool(getattr(asset, "preferred", False)),
        path=str(getattr(asset, "path", "") or ""),
        source=str(getattr(asset, "source", "") or ""),
    )


def _priority_map(rows: Iterable[ProductPriorityRow | dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        data = asdict(row) if isinstance(row, ProductPriorityRow) else dict(row) if isinstance(row, dict) else {}
        normalized = normalize_product_name(str(data.get("normalized_name") or data.get("display_name") or ""))
        if normalized:
            result[normalized] = data
    return result


def _load_thumbnail(path: str, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    try:
        with Image.open(path) as source:
            rgba = source.convert("RGBA")
            rgba.thumbnail(size, Image.Resampling.LANCZOS)
            tile = Image.new("RGBA", size, "white")
            x = (target_w - rgba.width) // 2
            y = (target_h - rgba.height) // 2
            tile.alpha_composite(rgba, (x, y))
            return tile.convert("RGB")
    except (OSError, ValueError):
        tile = Image.new("RGB", size, "white")
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, 0, target_w - 1, target_h - 1), outline="black")
        draw.text((10, 10), "imagem indisponivel", fill="black", font=ImageFont.load_default())
        return tile


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gera dataset/contact sheet da fila Produto↔Imagem por impacto.")
    parser.add_argument("--library", required=True)
    parser.add_argument("--corpus-source", action="append", default=[])
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--sheet", default=None)
    parser.add_argument("--max-products", type=int, default=60)
    parser.add_argument("--candidates-per-product", type=int, default=4)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    priority_rows: Iterable[ProductPriorityRow] = ()
    warnings: list[str] = []
    if args.corpus_source:
        report = scan_product_priority(args.corpus_source)
        priority_rows = report.rows
        warnings.extend(report.warnings)
    groups = build_review_dataset(
        SafeImageLibrary(args.library),
        priority_rows=priority_rows,
        max_products=args.max_products,
        candidates_per_product=args.candidates_per_product,
    )
    dataset_path = write_dataset(args.dataset, groups)
    output = {"dataset": str(dataset_path), **dataset_payload(groups)}
    if args.sheet:
        output["sheet"] = str(render_contact_sheet(groups, args.sheet, candidates_per_row=args.candidates_per_product))
    if warnings:
        output["warnings"] = list(dict.fromkeys(warnings))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
