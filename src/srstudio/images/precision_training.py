from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from srstudio.images.association import AssociationEvidence, normalize_product_name, spatial_pair_score
from srstudio.images.corpus_training import (
    CorpusTrainingReport,
    ProductImageCorpusTrainer,
    _ImageCandidate,
    _PRICE_TEXT_RE,
    sha256_file,
)


PRECISION_TRAINER_VERSION = "g2-image-precision-v2"


class PrecisionProductImageCorpusTrainer(ProductImageCorpusTrainer):
    """Precision-first pairing policy for the real Canva/PPTX corpus.

    Canva commonly repeats the same embedded media in two or more shape fills on
    one slide. Those shapes are a single logical image and must not compete with
    each other. A one-product/one-logical-image slide is also useful evidence even
    when Canva's transparent shape bbox makes the geometric score weak; in that
    special case the observation is retained but capped below auto-accept.

    Consensus also uses a logical-document fingerprint. Two files that differ only
    by package metadata/export copy but contain the same product/image evidence do
    not get to vote twice. This deliberately prefers precision over recall.
    """

    def train(self, sources: Iterable[str | Path], *, force: bool = False) -> CorpusTrainingReport:
        source_items = list(sources)
        if force:
            return super().train(source_items, force=True)

        state_before = self.state.load()
        records = state_before.get("files", {}) if isinstance(state_before, dict) else {}
        discovered_warnings: list[str] = []
        discovered = self.discover_sources(source_items, warnings=discovered_warnings)
        stale_sources: list[Path] = []
        fresh_sources: list[Path] = []

        for source in discovered:
            try:
                digest = sha256_file(source)
            except OSError:
                fresh_sources.append(source)
                continue
            record = records.get(digest) if isinstance(records, dict) else None
            if isinstance(record, dict) and record.get("precision_trainer_version") != PRECISION_TRAINER_VERSION:
                stale_sources.append(source)
            else:
                fresh_sources.append(source)

        # Process normal/new sources once. Existing current-version records are
        # skipped by the base trainer as usual.
        report = super().train(fresh_sources, force=False)

        # Reprocess only the stale subset, but do it in one pass. This keeps the
        # precision-policy upgrade incremental while avoiding repeated consensus
        # rebuilds/library learning when many old records are present.
        stale_processed = 0
        stale_processed_files: list[str] = []
        stale_warnings: list[str] = []
        if stale_sources:
            stale_report = super().train(stale_sources, force=True)
            stale_processed = stale_report.metrics.files_processed
            stale_processed_files.extend(stale_report.processed_files)
            stale_warnings.extend(stale_report.warnings)

        # Re-resolve the full active state without forcing work. This final call
        # returns consensus/coverage metrics while all current-version records are
        # skipped. We then restore batch execution counters from the actual work.
        if stale_sources:
            final_report = super().train(discovered, force=False)
            final_report.processed_files = list(
                dict.fromkeys([*report.processed_files, *stale_processed_files])
            )
            processed_set = set(final_report.processed_files)
            final_report.skipped_files = [
                path for path in final_report.skipped_files if path not in processed_set
            ]
            final_report.metrics.files_processed = report.metrics.files_processed + stale_processed
            final_report.metrics.files_skipped = len(final_report.skipped_files)
            final_report.warnings = list(
                dict.fromkeys(
                    [
                        *discovered_warnings,
                        *report.warnings,
                        *stale_warnings,
                        *final_report.warnings,
                        (
                            f"Precision trainer upgraded to {PRECISION_TRAINER_VERSION}; reprocessed "
                            f"{stale_processed} stale source(s) without forcing unchanged sources."
                        ),
                    ]
                )
            )
            return final_report

        report.warnings = list(dict.fromkeys([*discovered_warnings, *report.warnings]))
        return report

    def _process_pptx(self, source, digest: str) -> dict:
        record = super()._process_pptx(source, digest)
        source_document_id = self._logical_document_fingerprint(record)
        record["source_document_id"] = source_document_id
        record["precision_trainer_version"] = PRECISION_TRAINER_VERSION
        for item in record.get("evidence", []):
            if not isinstance(item, dict):
                continue
            metadata = dict(item.get("metadata", {}) or {})
            metadata["source_document_id"] = source_document_id
            metadata["source_sha256"] = digest
            item["metadata"] = metadata
        return record

    @staticmethod
    def _logical_document_fingerprint(record: dict) -> str:
        # Product/image pairs are more stable across Canva/PowerPoint export copies
        # than package-level bytes or relationship IDs. Bboxes are intentionally
        # excluded so harmless export rounding cannot manufacture a new source.
        evidence_pairs = []
        for item in record.get("evidence", []):
            if not isinstance(item, dict):
                continue
            evidence_pairs.append(
                (
                    int(item.get("source_slide", 0) or 0),
                    normalize_product_name(str(item.get("product_name", ""))),
                    str(item.get("image_sha256", "")),
                )
            )
        evidence_pairs.sort()
        payload = {
            "slides": int(record.get("slides", 0) or 0),
            "raw_image_refs": int(record.get("raw_image_refs", 0) or 0),
            "image_sha256": sorted(str(value) for value in record.get("image_sha256", []) if value),
            "product_names": sorted(
                normalize_product_name(str(value))
                for value in record.get("product_names", [])
                if normalize_product_name(str(value))
            ),
            "evidence_pairs": evidence_pairs,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

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

        # Precision first: recurring template assets are excluded whenever the
        # slide has at least one non-template candidate. Global consensus handles
        # the all-template fallback without making backgrounds win local geometry.
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
        used_sha256: set[str] = set()
        unique_sha256 = {image.sha256 for image in images}
        singleton_logical_pair = len(texts) == 1 and len(unique_sha256) == 1
        result: list[AssociationEvidence] = []

        for score, text_index, image_index, signals in candidates:
            image = images[image_index]
            if text_index in used_text or image.sha256 in used_sha256:
                continue

            minimum_score = 0.18 if singleton_logical_pair else 0.39
            if score < minimum_score:
                continue

            text = texts[text_index]
            alternate_scores = sorted(
                (
                    item[0]
                    for item in candidates
                    if item[1] == text_index and images[item[2]].sha256 != image.sha256
                ),
                reverse=True,
            )
            margin = score - (alternate_scores[0] if alternate_scores else 0.0)
            confidence = 0.50 + 0.34 * score + min(0.10, max(0.0, margin) * 0.5)
            if len(unique_sha256) == 1:
                confidence += 0.08
            if singleton_logical_pair:
                confidence += 0.05

            price_signal = self._has_nearby_price(text, image, prices, slide.width, slide.height)
            if price_signal:
                confidence += 0.03
            confidence = max(0.0, min(0.985, confidence))

            # Weak geometry from transparent Canva bbox is useful evidence but is
            # never enough by itself to cross the 0.90 automatic approval gate.
            if singleton_logical_pair and score < 0.39:
                confidence = min(confidence, 0.89)

            name_bbox = (int(text.x), int(text.y), int(text.width), int(text.height))
            metadata = {
                "pair_score": round(score, 6),
                "margin": round(margin, 6),
                "product_likelihood": round(image.product_likelihood, 6),
                "reuse_ratio": round(image.reuse_ratio, 6),
                "template_asset": image.template_asset,
                "price_signal": price_signal,
                "logical_image_sha256": image.sha256,
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
            used_sha256.add(image.sha256)

        return result
