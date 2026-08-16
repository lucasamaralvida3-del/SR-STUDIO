from __future__ import annotations

"""Triagem espacial para diferenças detectadas pelo SR Visual Fidelity Lab.

O score global informa *quanto* a renderização divergiu. Este módulo responde a
pergunta seguinte: *onde* estão as diferenças mais importantes? Ele divide a
página em tiles, agrupa regiões vizinhas e gera uma lista ordenada por impacto,
sem depender de NumPy. Assim um Golden Master real consegue apontar primeiro
para preço, tipografia, imagem/crop ou qualquer outro bloco que concentre o
maior erro visual.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import math
import sys

from PIL import Image, ImageChops, ImageStat


@dataclass(slots=True, frozen=True)
class FidelityRegion:
    x: int
    y: int
    width: int
    height: int
    changed_pixels: int
    total_pixels: int
    changed_ratio: float
    mean_error: float
    max_error: int
    importance: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class FidelityTriageReport:
    width: int
    height: int
    pixel_tolerance: int
    changed_pixels: int
    total_pixels: int
    changed_ratio: float
    mean_error: float
    max_error: int
    bbox: tuple[int, int, int, int] | None
    regions: tuple[FidelityRegion, ...]

    @property
    def clean(self) -> bool:
        return self.changed_pixels == 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["bbox"] = list(self.bbox) if self.bbox is not None else None
        payload["regions"] = [region.to_dict() for region in self.regions]
        return payload


def analyze_fidelity_regions(
    reference: str | Path,
    candidate: str | Path,
    *,
    pixel_tolerance: int = 12,
    tile_size: int = 64,
    min_tile_changed_ratio: float = 0.01,
    max_regions: int = 10,
    heatmap_path: str | Path | None = None,
) -> FidelityTriageReport:
    """Localiza e ordena as regiões de maior divergência entre duas imagens.

    ``pixel_tolerance`` usa a mesma ideia do Fidelity Lab: um pixel só entra na
    máscara quando a maior diferença entre os canais RGB ultrapassa a
    tolerância. Tiles adjacentes são unidos antes do cálculo final, evitando
    dezenas de pequenos alertas para um único preço ou fotografia.
    """

    tolerance = max(0, min(255, int(pixel_tolerance)))
    tile = max(8, int(tile_size))
    minimum_ratio = max(0.0, min(1.0, float(min_tile_changed_ratio)))
    region_limit = max(1, int(max_regions))

    ref_path = Path(reference)
    candidate_path = Path(candidate)
    with Image.open(ref_path) as raw_reference, Image.open(candidate_path) as raw_candidate:
        ref = raw_reference.convert("RGB")
        cand = raw_candidate.convert("RGB")
        if ref.size != cand.size:
            raise ValueError(
                "Triagem visual exige imagens com o mesmo tamanho: "
                f"referência={ref.size[0]}×{ref.size[1]}, candidata={cand.size[0]}×{cand.size[1]}."
            )
        width, height = ref.size
        difference = ImageChops.difference(ref, cand)

    red, green, blue = difference.split()
    max_channel = ImageChops.lighter(red, ImageChops.lighter(green, blue))
    mask = max_channel.point(lambda value: 255 if value > tolerance else 0, mode="L")
    changed_pixels = _mask_count(mask)
    total_pixels = max(1, width * height)
    bbox = mask.getbbox()

    if heatmap_path is not None:
        _save_heatmap(max_channel, mask, Path(heatmap_path))

    if changed_pixels == 0 or bbox is None:
        return FidelityTriageReport(
            width=width,
            height=height,
            pixel_tolerance=tolerance,
            changed_pixels=0,
            total_pixels=total_pixels,
            changed_ratio=0.0,
            mean_error=0.0,
            max_error=0,
            bbox=None,
            regions=(),
        )

    global_stats = ImageStat.Stat(max_channel, mask=mask)
    hot_tiles: set[tuple[int, int]] = set()
    tile_scores: dict[tuple[int, int], tuple[int, float]] = {}
    columns = math.ceil(width / tile)
    rows = math.ceil(height / tile)

    for row in range(rows):
        top = row * tile
        bottom = min(height, top + tile)
        for column in range(columns):
            left = column * tile
            right = min(width, left + tile)
            box = (left, top, right, bottom)
            tile_mask = mask.crop(box)
            changed = _mask_count(tile_mask)
            if changed <= 0:
                continue
            area = max(1, (right - left) * (bottom - top))
            ratio = changed / area
            stats = ImageStat.Stat(max_channel.crop(box), mask=tile_mask)
            mean_error = float(stats.mean[0] if stats.mean else 0.0)
            tile_scores[(column, row)] = (changed, mean_error)
            if ratio >= minimum_ratio:
                hot_tiles.add((column, row))

    # Uma divergência extremamente pequena ainda deve ser localizável. Se
    # nenhum tile passou o limiar, mantém o tile com maior impacto.
    if not hot_tiles and tile_scores:
        hottest = max(tile_scores, key=lambda key: tile_scores[key][0] * tile_scores[key][1])
        hot_tiles.add(hottest)

    regions: list[FidelityRegion] = []
    for component in _components(hot_tiles):
        min_column = min(item[0] for item in component)
        max_column = max(item[0] for item in component)
        min_row = min(item[1] for item in component)
        max_row = max(item[1] for item in component)
        rough = (
            min_column * tile,
            min_row * tile,
            min(width, (max_column + 1) * tile),
            min(height, (max_row + 1) * tile),
        )
        local_mask = mask.crop(rough)
        local_bbox = local_mask.getbbox()
        if local_bbox is None:
            continue
        refined = (
            rough[0] + local_bbox[0],
            rough[1] + local_bbox[1],
            rough[0] + local_bbox[2],
            rough[1] + local_bbox[3],
        )
        region_mask = mask.crop(refined)
        region_error = max_channel.crop(refined)
        changed = _mask_count(region_mask)
        region_width = max(1, refined[2] - refined[0])
        region_height = max(1, refined[3] - refined[1])
        area = region_width * region_height
        stats = ImageStat.Stat(region_error, mask=region_mask)
        mean_error = float(stats.mean[0] if stats.mean else 0.0)
        extrema = stats.extrema[0] if stats.extrema else (0, 0)
        max_error = int(extrema[1])
        regions.append(
            FidelityRegion(
                x=refined[0],
                y=refined[1],
                width=region_width,
                height=region_height,
                changed_pixels=changed,
                total_pixels=area,
                changed_ratio=changed / max(1, area),
                mean_error=mean_error,
                max_error=max_error,
                importance=float(changed) * mean_error,
            )
        )

    regions.sort(key=lambda item: (item.importance, item.changed_pixels, item.max_error), reverse=True)
    return FidelityTriageReport(
        width=width,
        height=height,
        pixel_tolerance=tolerance,
        changed_pixels=changed_pixels,
        total_pixels=total_pixels,
        changed_ratio=changed_pixels / total_pixels,
        mean_error=float(global_stats.mean[0] if global_stats.mean else 0.0),
        max_error=int(global_stats.extrema[0][1] if global_stats.extrema else 0),
        bbox=tuple(int(value) for value in bbox),
        regions=tuple(regions[:region_limit]),
    )


def write_triage_report(report: FidelityTriageReport, output: str | Path) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _mask_count(mask: Image.Image) -> int:
    histogram = mask.histogram()
    return int(histogram[255]) if len(histogram) > 255 else 0


def _components(points: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(points)
    result: list[set[tuple[int, int]]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            x, y = stack.pop()
            for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbour not in remaining:
                    continue
                remaining.remove(neighbour)
                component.add(neighbour)
                stack.append(neighbour)
        result.append(component)
    return result


def _save_heatmap(max_channel: Image.Image, mask: Image.Image, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Mantém somente diferenças acima da tolerância e amplia a intensidade para
    # que antialiasing/regiões de erro fiquem fáceis de inspecionar.
    visible = Image.new("L", max_channel.size, 0)
    visible.paste(max_channel.point(lambda value: min(255, value * 3)), mask=mask)
    visible.save(target, "PNG")


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="sr-fidelity-triage",
        description="Localiza automaticamente as regiões de maior diferença entre referência e render G2.",
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--out", type=Path, default=Path("build/fidelity/triage.json"))
    parser.add_argument("--heatmap", type=Path, default=Path("build/fidelity/triage-heatmap.png"))
    parser.add_argument("--pixel-tolerance", type=int, default=12)
    parser.add_argument("--tile-size", type=int, default=64)
    parser.add_argument("--min-tile-changed-ratio", type=float, default=0.01)
    parser.add_argument("--max-regions", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = analyze_fidelity_regions(
            args.reference,
            args.candidate,
            pixel_tolerance=args.pixel_tolerance,
            tile_size=args.tile_size,
            min_tile_changed_ratio=args.min_tile_changed_ratio,
            max_regions=args.max_regions,
            heatmap_path=args.heatmap,
        )
        write_triage_report(report, args.out)
    except Exception as exc:
        print(f"SR Fidelity Triage: ERRO: {exc}", file=sys.stderr)
        return 2

    print(
        "SR Fidelity Triage: "
        f"{report.changed_ratio * 100:.3f}% da página alterada · "
        f"{len(report.regions)} região(ões) prioritária(s) · relatório {args.out}"
    )
    for index, region in enumerate(report.regions, start=1):
        print(
            f"  #{index}: x={region.x} y={region.y} {region.width}×{region.height} · "
            f"{region.changed_ratio * 100:.2f}% · erro médio {region.mean_error:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
