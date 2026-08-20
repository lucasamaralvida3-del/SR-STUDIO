from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import time
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageStat

from srstudio.images.association import (
    AssociationDecision,
    AssociationEvidence,
    ProductImageAssociationEngine,
    is_likely_template_asset,
    is_product_text_candidate,
    normalize_product_name,
    spatial_pair_score,
)


_TRAINER_VERSION = "g2-image-corpus-v1"
_STATE_SCHEMA_VERSION = 1
_PRICE_TEXT_RE = re.compile(r"(?:R\$\s*)?\d{1,4}\s*[,.]\s*\d{2}", re.IGNORECASE)


class CorpusStateError(RuntimeError):
    pass


@dataclass(slots=True)
class CorpusTrainingMetrics:
    files_discovered: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    slides: int = 0
    raw_image_refs: int = 0
    unique_image_sha256: int = 0
    recurring_template_assets: int = 0
    product_text_candidates: int = 0
    unique_products: int = 0
    observations: int = 0
    unique_associated_images: int = 0
    accepted: int = 0
    probable: int = 0
    review: int = 0
    decorative: int = 0
    products_with_image: int = 0
    products_without_image: int = 0
    unmatched_images: int = 0
    images_learned: int = 0
    elapsed_seconds: float = 0.0


@dataclass(slots=True)
class CorpusTrainingReport:
    metrics: CorpusTrainingMetrics
    decisions: list[AssociationDecision] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    processed_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _ImageCandidate:
    sha256: str
    media_path: str
    shape_name: str
    relationship_id: str
    bbox: tuple[int, int, int, int]
    z_order: int
    group_name: str
    area_ratio: float
    product_likelihood: float = 0.5
    template_asset: bool = False
    reuse_ratio: float = 0.0


class CorpusStateStore:
    """Fail-closed incremental evidence store with rollback backup."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CorpusStateError(f"Invalid corpus state {self.path}: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != _STATE_SCHEMA_VERSION:
            raise CorpusStateError(f"Unsupported corpus state schema in {self.path}")
        if not isinstance(payload.get("files"), dict):
            raise CorpusStateError(f"Invalid corpus state files mapping in {self.path}")
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.load()
            shutil.copy2(self.path, self.path.with_suffix(self.path.suffix + ".bak"))
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        json.loads(tmp.read_text(encoding="utf-8"))
        tmp.replace(self.path)

    @staticmethod
    def empty() -> dict[str, Any]:
        return {
            "schema_version": _STATE_SCHEMA_VERSION,
            "trainer_version": _TRAINER_VERSION,
            "updated_at": "",
            "files": {},
        }


class ProductImageCorpusTrainer:
    """Incrementally train Product↔Image associations from structured Canva/PPTX files."""

    def __init__(
        self,
        library: Any,
        *,
        imports_root: str | Path,
        state_path: str | Path | None = None,
        importer: Any | None = None,
        association_engine: ProductImageAssociationEngine | None = None,
    ) -> None:
        self.library = library
        self.imports_root = Path(imports_root)
        self.imports_root.mkdir(parents=True, exist_ok=True)
        self.state = CorpusStateStore(state_path or (self.imports_root / "image_corpus_state.json"))
        if importer is None:
            from srstudio.importers.pptx.reader import PptxImporter

            importer = PptxImporter()
        self.importer = importer
        self.engine = association_engine or ProductImageAssociationEngine()
        self._feature_cache: dict[str, dict[str, float]] = {}

    def train(self, sources: Iterable[str | Path], *, force: bool = False) -> CorpusTrainingReport:
        started = time.perf_counter()
        warnings: list[str] = []
        discovered = self.discover_sources(sources, warnings=warnings)
        metrics = CorpusTrainingMetrics(files_discovered=len(discovered))
        payload = self.state.load()
        payload["trainer_version"] = _TRAINER_VERSION
        active_records = payload.setdefault("files", {})
        processed: list[str] = []
        skipped: list[str] = []

        for source in discovered:
            try:
                digest = sha256_file(source)
            except OSError as exc:
                warnings.append(f"{source}: cannot hash source: {exc}")
                continue
            existing = active_records.get(digest)
            if existing and existing.get("trainer_version") == _TRAINER_VERSION and not force:
                metrics.files_skipped += 1
                skipped.append(str(source))
                continue
            try:
                record = self._process_pptx(source, digest)
            except Exception as exc:
                warnings.append(f"{source}: {exc}")
                continue

            source_key = str(source.resolve())
            for old_digest, old_record in active_records.items():
                if old_digest == digest or not isinstance(old_record, dict):
                    continue
                if old_record.get("source_path") == source_key and old_record.get("active", True):
                    old_record["active"] = False
                    old_record["superseded_by"] = digest

            active_records[digest] = record
            for warning in record.get("import_warnings", []):
                warnings.append(f"{source.name}: {warning}")
            metrics.files_processed += 1
            processed.append(str(source))

        all_evidence: list[AssociationEvidence] = []
        all_product_names: set[str] = set()
        all_image_sha: set[str] = set()
        recurring_template_sha: set[str] = set()
        total_slides = 0
        total_refs = 0
        total_texts = 0
        for record in active_records.values():
            if not isinstance(record, dict) or not record.get("active", True):
                continue
            if record.get("trainer_version") != _TRAINER_VERSION:
                continue
            total_slides += int(record.get("slides", 0))
            total_refs += int(record.get("raw_image_refs", 0))
            total_texts += int(record.get("product_text_candidates", 0))
            all_image_sha.update(str(value) for value in record.get("image_sha256", []) if value)
            recurring_template_sha.update(str(value) for value in record.get("template_sha256", []) if value)
            all_product_names.update(str(value) for value in record.get("product_names", []) if value)
            for item in record.get("evidence", []):
                try:
                    all_evidence.append(_evidence_from_dict(item))
                except Exception as exc:
                    warnings.append(f"Invalid saved evidence ignored: {exc}")

        decisions = self.engine.resolve(all_evidence)
        associated_sha = {decision.image_sha256 for decision in decisions if decision.status != "decorative"}
        associated_products = {
            decision.normalized_name for decision in decisions if decision.status in {"accepted", "probable", "review"}
        }

        metrics.slides = total_slides
        metrics.raw_image_refs = total_refs
        metrics.product_text_candidates = total_texts
        metrics.unique_image_sha256 = len(all_image_sha)
        metrics.recurring_template_assets = len(recurring_template_sha)
        metrics.unique_products = len(all_product_names)
        metrics.observations = len(all_evidence)
        metrics.unique_associated_images = len({decision.image_sha256 for decision in decisions})
        metrics.accepted = sum(decision.status == "accepted" for decision in decisions)
        metrics.probable = sum(decision.status == "probable" for decision in decisions)
        metrics.review = sum(decision.status == "review" for decision in decisions)
        metrics.decorative = sum(decision.status == "decorative" for decision in decisions)
        metrics.products_with_image = len(associated_products)
        metrics.products_without_image = len(all_product_names - associated_products)
        metrics.unmatched_images = len(all_image_sha - associated_sha - recurring_template_sha)

        state_changed = metrics.files_processed > 0 or force or not self.state.path.exists()
        for decision in decisions:
            if not state_changed or decision.status == "decorative" or not decision.evidence:
                continue
            canonical = decision.evidence[0]
            media_path = Path(canonical.media_path)
            if not media_path.exists():
                warnings.append(f"Missing extracted media for {decision.product_name}: {media_path}")
                continue
            provenance = [
                {
                    "source_file": item.source_file,
                    "source_slide": item.source_slide,
                    "source_shape": item.source_shape,
                    "relationship_id": item.relationship_id,
                    "media_path": item.media_path,
                    "confidence": round(item.confidence, 6),
                    "match_method": item.match_method,
                    "image_bbox": list(item.image_bbox),
                    "name_bbox": list(item.name_bbox),
                }
                for item in decision.evidence
            ]
            metadata = {
                "sha256": decision.image_sha256,
                "normalized_name": decision.normalized_name,
                "association_status": decision.status,
                "association_confidence": decision.confidence,
                "consensus_ratio": decision.consensus_ratio,
                "source_count": decision.source_count,
                "distinct_source_count": decision.distinct_source_count,
                "match_method": "corpus-consensus-v1",
                "provenance": provenance,
                "alternatives": [asdict(item) for item in decision.alternatives],
            }
            library_gate = float(getattr(self.library, "AUTO_ACCEPT_CONFIDENCE", 0.82))
            learn_confidence = decision.confidence
            if decision.status != "accepted":
                learn_confidence = min(decision.confidence, max(0.0, library_gate - 0.001))
            asset = self.library.learn_product_image(
                media_path,
                decision.product_name,
                confidence=learn_confidence,
                source_file=canonical.source_file,
                slide_index=canonical.source_slide,
                metadata=metadata,
            )
            if decision.status != "accepted" and hasattr(self.library, "update_metadata") and getattr(asset, "id", None):
                self.library.update_metadata(
                    asset.id,
                    confidence=decision.confidence,
                    review_status="pending",
                    metadata=metadata,
                )
            metrics.images_learned += 1

        if state_changed:
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            self.state.save(payload)
        metrics.elapsed_seconds = round(time.perf_counter() - started, 4)
        return CorpusTrainingReport(metrics, decisions, warnings, processed, skipped)

    def _process_pptx(self, source: Path, digest: str) -> dict[str, Any]:
        media_dir = self.imports_root / "media" / digest[:24]
        imported = self.importer.import_file(source, media_dir=media_dir)
        slide_count = len(imported.slides)
        usage: dict[str, set[int]] = defaultdict(set)
        image_sha: set[str] = set()
        raw_refs = 0
        texts_by_slide: dict[int, list[Any]] = {}
        images_by_slide: dict[int, list[_ImageCandidate]] = {}
        product_names: set[str] = set()

        for slide in imported.slides:
            texts = [element for element in slide.elements if element.kind == "text" and is_product_text_candidate(element.text)]
            texts_by_slide[slide.index] = texts
            product_names.update(normalize_product_name(element.text) for element in texts)
            image_rows: list[_ImageCandidate] = []
            slide_area = max(1, slide.width * slide.height)
            for element in slide.elements:
                if element.kind != "image" or not element.media_path:
                    continue
                media_path = Path(element.media_path)
                if not media_path.exists():
                    continue
                sha256 = sha256_file(media_path)
                raw_refs += 1
                image_sha.add(sha256)
                usage[sha256].add(slide.index)
                metadata = element.metadata or {}
                image_rows.append(
                    _ImageCandidate(
                        sha256=sha256,
                        media_path=str(media_path),
                        shape_name=element.name or "",
                        relationship_id=str(metadata.get("relationship_id", "")),
                        bbox=(int(element.x), int(element.y), int(element.width), int(element.height)),
                        z_order=int(metadata.get("z_index", 0) or 0),
                        group_name=str(metadata.get("group_name", "") or ""),
                        area_ratio=(int(element.width) * int(element.height)) / slide_area,
                    )
                )
            images_by_slide[slide.index] = image_rows

        template_sha = {
            sha256
            for sha256, slides in usage.items()
            if is_likely_template_asset(slides_with_asset=len(slides), total_slides=slide_count)
        }
        evidence: list[AssociationEvidence] = []
        for slide in imported.slides:
            evidence.extend(
                self._pair_slide(
                    slide,
                    texts_by_slide.get(slide.index, []),
                    images_by_slide.get(slide.index, []),
                    usage,
                    slide_count,
                    template_sha,
                    source.name,
                )
            )

        return {
            "source_file": source.name,
            "source_path": str(source.resolve()),
            "source_sha256": digest,
            "trainer_version": _TRAINER_VERSION,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "active": True,
            "slides": slide_count,
            "raw_image_refs": raw_refs,
            "image_sha256": sorted(image_sha),
            "template_sha256": sorted(template_sha),
            "product_text_candidates": sum(len(value) for value in texts_by_slide.values()),
            "product_names": sorted(name for name in product_names if name),
            "evidence": [_evidence_to_dict(item) for item in evidence],
            "import_warnings": list(getattr(imported, "warnings", []) or []),
        }

    def _pair_slide(
        self,
        slide: Any,
        texts: list[Any],
        images: list[_ImageCandidate],
        usage: dict[str, set[int]],
        slide_count: int,
        template_sha: set[str],
        source_file: str,
    ) -> list[AssociationEvidence]:
        if not texts or not images:
            return []
        viable: list[_ImageCandidate] = []
        fallback: list[_ImageCandidate] = []
        for image in images:
            if image.area_ratio < 0.0008 or image.area_ratio > 0.95:
                continue
            image.product_likelihood = self._product_likelihood(image.sha256, image.media_path, image.area_ratio)
            slides_with = len(usage.get(image.sha256, ()))
            image.reuse_ratio = slides_with / max(1, slide_count)
            image.template_asset = image.sha256 in template_sha
            features = self._feature_cache.get(image.sha256, {})
            if features.get("rgb_std", 99.0) < 5.0 and features.get("color_bins", 99.0) <= 4.0:
                continue
            fallback.append(image)
            if not image.template_asset:
                viable.append(image)
        images = viable or fallback
        if not images:
            return []

        prices = [element for element in slide.elements if element.kind == "text" and _PRICE_TEXT_RE.search(element.text or "")]
        candidates: list[tuple[float, int, int, dict[str, float]]] = []
        for text_index, text in enumerate(texts):
            name_bbox = (int(text.x), int(text.y), int(text.width), int(text.height))
            text_group = str((text.metadata or {}).get("group_name", "") or "")
            text_z = int((text.metadata or {}).get("z_index", 0) or 0)
            for image_index, image in enumerate(images):
                same_group = bool(text_group and image.group_name and text_group == image.group_name)
                score, signals = spatial_pair_score(
                    image.bbox,
                    name_bbox,
                    slide_width=int(slide.width),
                    slide_height=int(slide.height),
                    product_likelihood=image.product_likelihood,
                    same_group=same_group,
                    z_distance=image.z_order - text_z,
                )
                candidates.append((score, text_index, image_index, signals))

        candidates.sort(key=lambda item: item[0], reverse=True)
        used_text: set[int] = set()
        used_image: set[int] = set()
        result: list[AssociationEvidence] = []
        for score, text_index, image_index, signals in candidates:
            if text_index in used_text or image_index in used_image or score < 0.39:
                continue
            text = texts[text_index]
            image = images[image_index]
            alternate_scores = sorted(
                (item[0] for item in candidates if item[1] == text_index and item[2] != image_index),
                reverse=True,
            )
            margin = score - (alternate_scores[0] if alternate_scores else 0.0)
            confidence = 0.50 + 0.34 * score + min(0.10, max(0.0, margin) * 0.5)
            if len(images) == 1:
                confidence += 0.08
            if len(images) == 1 and len(texts) == 1:
                confidence += 0.05
            price_signal = self._has_nearby_price(text, image, prices, slide.width, slide.height)
            if price_signal:
                confidence += 0.03
            confidence = max(0.0, min(0.985, confidence))
            name_bbox = (int(text.x), int(text.y), int(text.width), int(text.height))
            metadata = {
                "pair_score": round(score, 6),
                "margin": round(margin, 6),
                "product_likelihood": round(image.product_likelihood, 6),
                "reuse_ratio": round(image.reuse_ratio, 6),
                "template_asset": image.template_asset,
                "price_signal": price_signal,
                **signals,
            }
            result.append(
                AssociationEvidence(
                    product_name=text.text,
                    image_sha256=image.sha256,
                    confidence=confidence,
                    source_file=source_file,
                    source_slide=int(slide.index),
                    source_shape=image.shape_name,
                    relationship_id=image.relationship_id,
                    media_path=image.media_path,
                    image_bbox=image.bbox,
                    name_bbox=name_bbox,
                    z_order=image.z_order,
                    group_name=image.group_name,
                    metadata=metadata,
                )
            )
            used_text.add(text_index)
            used_image.add(image_index)
        return result

    def _product_likelihood(self, sha256: str, media_path: str, area_ratio: float) -> float:
        features = self._feature_cache.get(sha256)
        if features is None:
            features = image_features(media_path)
            self._feature_cache[sha256] = features
        transparency = features.get("transparent_ratio", 0.0)
        rgb_std = features.get("rgb_std", 0.0)
        color_bins = features.get("color_bins", 0.0)
        aspect = features.get("aspect", 1.0)
        score = 0.50
        if 0.04 <= transparency <= 0.96:
            score += 0.14
        elif transparency > 0.995:
            score -= 0.12
        score += 0.09 if rgb_std >= 35 else (-0.22 if rgb_std < 12 else 0.0)
        score += 0.05 if color_bins >= 12 else (-0.14 if color_bins <= 3 else 0.0)
        score += 0.05 if 0.28 <= aspect <= 3.2 else (-0.15 if aspect > 5 or aspect < 0.15 else 0.0)
        score += 0.04 if 0.004 <= area_ratio <= 0.75 else (-0.18 if area_ratio > 0.92 else 0.0)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _has_nearby_price(text: Any, image: _ImageCandidate, prices: list[Any], width: int, height: int) -> bool:
        if not prices:
            return False
        diag = max(math.hypot(width, height), 1.0)
        tx = int(text.x) + int(text.width) / 2.0
        ty = int(text.y) + int(text.height) / 2.0
        ix, iy, iw, ih = image.bbox
        cx = (tx + ix + iw / 2.0) / 2.0
        cy = (ty + iy + ih / 2.0) / 2.0
        for price in prices:
            px = int(price.x) + int(price.width) / 2.0
            py = int(price.y) + int(price.height) / 2.0
            if math.hypot(px - cx, py - cy) / diag <= 0.18:
                return True
        return False

    def discover_sources(self, sources: Iterable[str | Path], *, warnings: list[str] | None = None) -> list[Path]:
        warnings = warnings if warnings is not None else []
        discovered: list[Path] = []
        for item in sources:
            path = Path(item)
            if path.is_dir():
                discovered.extend(sorted(path.rglob("*.pptx")))
            elif path.suffix.lower() == ".pptx" and path.is_file():
                discovered.append(path)
            elif path.suffix.lower() == ".zip" and path.is_file():
                discovered.extend(self._extract_zip_pptx(path, warnings))
            else:
                warnings.append(f"Unsupported or missing corpus source: {path}")
        unique: dict[str, Path] = {}
        for path in discovered:
            try:
                unique[sha256_file(path)] = path
            except OSError as exc:
                warnings.append(f"{path}: {exc}")
        return list(unique.values())

    def _extract_zip_pptx(self, path: Path, warnings: list[str]) -> list[Path]:
        zip_digest = sha256_file(path)
        target = self.imports_root / "corpus_sources" / zip_digest[:24]
        target.mkdir(parents=True, exist_ok=True)
        result: list[Path] = []
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".pptx"):
                    continue
                safe_name = Path(member.filename).name
                if not safe_name:
                    continue
                destination = target / safe_name
                if not destination.exists() or destination.stat().st_size != member.file_size:
                    with archive.open(member) as src, destination.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                result.append(destination)
        if not result:
            warnings.append(f"No PPTX found in ZIP: {path}")
        return result


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_features(path: str | Path) -> dict[str, float]:
    with Image.open(path) as image:
        width, height = image.size
        rgba = image.convert("RGBA")
        rgba.thumbnail((96, 96))
        alpha = rgba.getchannel("A")
        alpha_hist = alpha.histogram()
        total = max(1, sum(alpha_hist))
        transparent_ratio = sum(alpha_hist[:245]) / total
        rgb = rgba.convert("RGB")
        rgb_stat = ImageStat.Stat(rgb)
        rgb_std = sum(rgb_stat.stddev) / 3.0
        quantized = rgb.quantize(colors=32)
        color_bins = sum(1 for count in quantized.histogram() if count)
        return {
            "width": float(width),
            "height": float(height),
            "aspect": width / max(height, 1),
            "transparent_ratio": transparent_ratio,
            "rgb_std": rgb_std,
            "color_bins": float(color_bins),
        }


def _evidence_to_dict(item: AssociationEvidence) -> dict[str, Any]:
    return {
        "product_name": item.product_name,
        "image_sha256": item.image_sha256,
        "confidence": item.confidence,
        "source_file": item.source_file,
        "source_slide": item.source_slide,
        "source_shape": item.source_shape,
        "relationship_id": item.relationship_id,
        "media_path": item.media_path,
        "image_bbox": list(item.image_bbox),
        "name_bbox": list(item.name_bbox),
        "z_order": item.z_order,
        "group_name": item.group_name,
        "match_method": item.match_method,
        "metadata": item.metadata,
    }


def _evidence_from_dict(item: dict[str, Any]) -> AssociationEvidence:
    return AssociationEvidence(
        product_name=str(item.get("product_name", "")),
        image_sha256=str(item.get("image_sha256", "")),
        confidence=float(item.get("confidence", 0.0)),
        source_file=str(item.get("source_file", "")),
        source_slide=int(item.get("source_slide", 0)),
        source_shape=str(item.get("source_shape", "")),
        relationship_id=str(item.get("relationship_id", "")),
        media_path=str(item.get("media_path", "")),
        image_bbox=tuple(int(value) for value in item.get("image_bbox", (0, 0, 0, 0))),
        name_bbox=tuple(int(value) for value in item.get("name_bbox", (0, 0, 0, 0))),
        z_order=int(item.get("z_order", 0)),
        group_name=str(item.get("group_name", "")),
        match_method=str(item.get("match_method", "spatial-template-filter-v1")),
        metadata=dict(item.get("metadata", {}) or {}),
    )
