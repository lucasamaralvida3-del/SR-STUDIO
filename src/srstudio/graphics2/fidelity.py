from __future__ import annotations

"""Métricas determinísticas de fidelidade visual do SR Graphics Engine 2.

O módulo é deliberadamente independente de Qt. Ele compara o bitmap de
referência com o bitmap produzido pelo engine e gera um resultado objetivo,
adequado para CI, relatórios e investigação manual.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
import json
import math

from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat


@dataclass(slots=True, frozen=True)
class FidelityPolicy:
    """Critérios mínimos para uma comparação visual ser aprovada."""

    min_score: float = 0.985
    min_pixel_pass_ratio: float = 0.965
    pixel_tolerance: int = 12
    max_changed_ratio: float = 0.035
    require_same_size: bool = True

    def normalized(self) -> "FidelityPolicy":
        return FidelityPolicy(
            min_score=min(1.0, max(0.0, float(self.min_score))),
            min_pixel_pass_ratio=min(1.0, max(0.0, float(self.min_pixel_pass_ratio))),
            pixel_tolerance=min(255, max(0, int(self.pixel_tolerance))),
            max_changed_ratio=min(1.0, max(0.0, float(self.max_changed_ratio))),
            require_same_size=bool(self.require_same_size),
        )


@dataclass(slots=True)
class FidelityMetrics:
    score: float
    color_similarity: float
    luminance_similarity: float
    edge_similarity: float
    pixel_pass_ratio: float
    changed_ratio: float
    mean_absolute_error: float
    rms_error: float
    width: int
    height: int
    baseline_width: int
    baseline_height: int
    candidate_width: int
    candidate_height: int
    changed_bbox: tuple[int, int, int, int] | None = None

    @property
    def percent(self) -> float:
        return self.score * 100.0


@dataclass(slots=True)
class FidelityResult:
    name: str
    passed: bool
    metrics: FidelityMetrics
    policy: FidelityPolicy
    reasons: list[str] = field(default_factory=list)
    baseline: str = ""
    candidate: str = ""
    diff_path: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["metrics"]["percent"] = round(self.metrics.percent, 6)
        return payload


@dataclass(slots=True, frozen=True)
class FidelityCase:
    name: str
    baseline: Path
    candidate: Path
    policy: FidelityPolicy = FidelityPolicy()


@dataclass(slots=True)
class FidelitySuiteResult:
    cases: list[FidelityResult]

    @property
    def passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)

    @property
    def average_score(self) -> float:
        if not self.cases:
            return 0.0
        return sum(case.metrics.score for case in self.cases) / len(self.cases)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "average_score": self.average_score,
            "average_percent": self.average_score * 100.0,
            "cases": [case.to_dict() for case in self.cases],
        }


def compare_images(
    baseline: str | Path,
    candidate: str | Path,
    *,
    name: str = "visual",
    policy: FidelityPolicy | None = None,
    diff_path: str | Path | None = None,
) -> FidelityResult:
    """Compara duas imagens e retorna métricas + decisão de gate.

    A dimensão original participa do gate. Quando os tamanhos são diferentes,
    a candidata é redimensionada somente para produzir métricas diagnósticas;
    com ``require_same_size=True`` o caso continua reprovado.
    """

    policy = (policy or FidelityPolicy()).normalized()
    baseline_path = Path(baseline)
    candidate_path = Path(candidate)
    with Image.open(baseline_path) as opened:
        reference = _flatten(opened)
    with Image.open(candidate_path) as opened:
        observed = _flatten(opened)

    reference_size = reference.size
    candidate_size = observed.size
    size_matches = reference_size == candidate_size
    if not size_matches:
        observed = observed.resize(reference_size, Image.Resampling.LANCZOS)

    metrics, difference = _measure(reference, observed, policy.pixel_tolerance)
    metrics.baseline_width, metrics.baseline_height = reference_size
    metrics.candidate_width, metrics.candidate_height = candidate_size

    reasons: list[str] = []
    if policy.require_same_size and not size_matches:
        reasons.append(
            f"dimensão divergente: referência {reference_size[0]}x{reference_size[1]}, "
            f"candidata {candidate_size[0]}x{candidate_size[1]}"
        )
    if metrics.score < policy.min_score:
        reasons.append(f"score {metrics.score:.6f} abaixo de {policy.min_score:.6f}")
    if metrics.pixel_pass_ratio < policy.min_pixel_pass_ratio:
        reasons.append(
            f"pixels dentro da tolerância {metrics.pixel_pass_ratio:.6f} abaixo de "
            f"{policy.min_pixel_pass_ratio:.6f}"
        )
    if metrics.changed_ratio > policy.max_changed_ratio:
        reasons.append(
            f"área alterada {metrics.changed_ratio:.6f} acima de {policy.max_changed_ratio:.6f}"
        )

    written_diff = ""
    if diff_path is not None:
        target = Path(diff_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _save_diff(reference, observed, difference, target)
        written_diff = str(target)

    return FidelityResult(
        name=name,
        passed=not reasons,
        metrics=metrics,
        policy=policy,
        reasons=reasons,
        baseline=str(baseline_path),
        candidate=str(candidate_path),
        diff_path=written_diff,
    )


def run_suite(
    cases: Iterable[FidelityCase],
    *,
    artifacts_dir: str | Path | None = None,
) -> FidelitySuiteResult:
    output = Path(artifacts_dir) if artifacts_dir is not None else None
    results: list[FidelityResult] = []
    for index, case in enumerate(cases, start=1):
        diff = None
        if output is not None:
            safe_name = _safe_name(case.name or f"case-{index}")
            diff = output / f"{index:03d}-{safe_name}-diff.png"
        results.append(
            compare_images(
                case.baseline,
                case.candidate,
                name=case.name,
                policy=case.policy,
                diff_path=diff,
            )
        )
    return FidelitySuiteResult(results)


def load_manifest(path: str | Path) -> list[FidelityCase]:
    source = Path(path)
    raw = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
        raise ValueError("Manifesto de fidelidade deve conter uma lista 'cases'.")
    manifest_defaults = FidelityPolicy()
    defaults = dict(raw.get("defaults") or {})
    result: list[FidelityCase] = []
    for index, item in enumerate(raw["cases"], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Caso {index} do manifesto é inválido.")
        merged = dict(defaults)
        merged.update(dict(item.get("policy") or {}))
        policy = FidelityPolicy(
            min_score=float(merged.get("min_score", manifest_defaults.min_score)),
            min_pixel_pass_ratio=float(
                merged.get("min_pixel_pass_ratio", manifest_defaults.min_pixel_pass_ratio)
            ),
            pixel_tolerance=int(merged.get("pixel_tolerance", manifest_defaults.pixel_tolerance)),
            max_changed_ratio=float(merged.get("max_changed_ratio", manifest_defaults.max_changed_ratio)),
            require_same_size=bool(merged.get("require_same_size", manifest_defaults.require_same_size)),
        ).normalized()
        baseline = _resolve_manifest_path(source.parent, item.get("baseline"), index, "baseline")
        candidate = _resolve_manifest_path(source.parent, item.get("candidate"), index, "candidate")
        result.append(FidelityCase(str(item.get("name") or f"case-{index}"), baseline, candidate, policy))
    return result


def write_report(result: FidelityResult | FidelitySuiteResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _measure(reference: Image.Image, observed: Image.Image, tolerance: int) -> tuple[FidelityMetrics, Image.Image]:
    difference = ImageChops.difference(reference, observed).convert("RGB")
    stat = ImageStat.Stat(difference)
    channel_means = stat.mean[:3]
    channel_rms = stat.rms[:3]
    mae = sum(channel_means) / (3.0 * 255.0)
    rms = math.sqrt(sum(value * value for value in channel_rms) / 3.0) / 255.0
    color_similarity = _clamp01(1.0 - mae)

    ref_luma = ImageOps.grayscale(reference)
    obs_luma = ImageOps.grayscale(observed)
    luma_diff = ImageChops.difference(ref_luma, obs_luma)
    luma_mae = ImageStat.Stat(luma_diff).mean[0] / 255.0
    luminance_similarity = _clamp01(1.0 - luma_mae)

    ref_edges = ref_luma.filter(ImageFilter.FIND_EDGES)
    obs_edges = obs_luma.filter(ImageFilter.FIND_EDGES)
    edge_mae = ImageStat.Stat(ImageChops.difference(ref_edges, obs_edges)).mean[0] / 255.0
    edge_similarity = _clamp01(1.0 - edge_mae)

    max_channel = difference.getextrema()
    if all(high <= tolerance for _low, high in max_channel):
        pixel_pass_ratio = 1.0
        changed_ratio = 0.0
        changed_bbox = None
    else:
        mask = _difference_mask(difference, tolerance)
        histogram = mask.histogram()
        total = reference.width * reference.height
        changed = total - histogram[0]
        changed_ratio = changed / total if total else 0.0
        pixel_pass_ratio = 1.0 - changed_ratio
        changed_bbox = mask.getbbox()

    # Cor preserva fidelidade fina; luminância evita falsos positivos por
    # pequenas variações cromáticas; bordas penalizam texto/objetos deslocados.
    score = _clamp01(
        color_similarity * 0.52
        + luminance_similarity * 0.18
        + edge_similarity * 0.30
    )

    return (
        FidelityMetrics(
            score=score,
            color_similarity=color_similarity,
            luminance_similarity=luminance_similarity,
            edge_similarity=edge_similarity,
            pixel_pass_ratio=pixel_pass_ratio,
            changed_ratio=changed_ratio,
            mean_absolute_error=mae,
            rms_error=rms,
            width=reference.width,
            height=reference.height,
            baseline_width=reference.width,
            baseline_height=reference.height,
            candidate_width=observed.width,
            candidate_height=observed.height,
            changed_bbox=changed_bbox,
        ),
        difference,
    )


def _flatten(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    background.alpha_composite(rgba)
    return background.convert("RGB")


def _difference_mask(difference: Image.Image, tolerance: int) -> Image.Image:
    # Um pixel é alterado se QUALQUER canal ultrapassar a tolerância.
    r, g, b = difference.split()
    threshold = lambda value: 255 if value > tolerance else 0
    return ImageChops.lighter(ImageChops.lighter(r.point(threshold), g.point(threshold)), b.point(threshold))


def _save_diff(reference: Image.Image, observed: Image.Image, difference: Image.Image, target: Path) -> None:
    # Artefato 3-up: referência | candidata | diferença amplificada.
    amplified = difference.point(lambda value: min(255, value * 4))
    canvas = Image.new("RGB", (reference.width * 3, reference.height), "white")
    canvas.paste(reference, (0, 0))
    canvas.paste(observed, (reference.width, 0))
    canvas.paste(amplified, (reference.width * 2, 0))
    canvas.save(target, "PNG", optimize=True)


def _resolve_manifest_path(root: Path, value: object, index: int, field_name: str) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Caso {index} sem '{field_name}'.")
    path = Path(text)
    return path if path.is_absolute() else (root / path).resolve()


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned.strip("-") or "visual"


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))
