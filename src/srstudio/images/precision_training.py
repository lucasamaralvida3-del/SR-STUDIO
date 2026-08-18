from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
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


PRECISION_TRAINER_VERSION = "g2-image-precision-v3"


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

    Phase 2 additionally keeps archive provenance independently from consensus:
    ZIP copies or alternate archive paths can all be audited, while an identical
    inner PPTX is still one logical source for confidence purposes.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._archive_provenance_by_pptx_sha: dict[str, list[dict[str, Any]]] = {}
        super().__init__(*args, **kwargs)

    def train(self, sources: Iterable[str | Path], *, force: bool = False) -> CorpusTrainingReport:
        source_items = list(sources)
        if force:
            return self._finalize_report(super().train(source_items, force=True))

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
            return self._finalize_report(final_report)

        report.warnings = list(dict.fromkeys([*discovered_warnings, *report.warnings]))
        return self._finalize_report(report)

    def _extract_zip_pptx(self, path: Path, warnings: list[str]) -> list[Path]:
        """Extract PPTX members safely while retaining immutable archive provenance."""
        zip_digest = sha256_file(path)
        target = self.imports_root / "corpus_sources" / zip_digest[:24]
        target.mkdir(parents=True, exist_ok=True)
        result: list[Path] = []

        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.lower().endswith(".pptx"):
                    continue
                basename = Path(member.filename).name
                if not basename:
                    continue

                # Do not flatten two different internal paths onto the same file.
                # The member-name digest is deterministic and archive-specific.
                member_key = hashlib.sha256(member.filename.encode("utf-8", errors="replace")).hexdigest()[:12]
                destination = target / f"{member_key}__{basename}"
                if not destination.exists() or destination.stat().st_size != member.file_size:
                    with archive.open(member) as src, destination.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

                try:
                    pptx_digest = sha256_file(destination)
                except OSError as exc:
                    warnings.append(f"{path}:{member.filename}: cannot hash extracted PPTX: {exc}")
                    continue

                provenance = {
                    "source_kind": "archive-pptx",
                    "source_archive": str(path.resolve()),
                    "source_archive_sha256": zip_digest,
                    "source_member": member.filename,
                    "source_member_size": int(member.file_size),
                    "source_member_crc32": f"{int(member.CRC) & 0xFFFFFFFF:08x}",
                    "source_pptx_sha256": pptx_digest,
                }
                rows = self._archive_provenance_by_pptx_sha.setdefault(pptx_digest, [])
                key = json.dumps(provenance, ensure_ascii=False, sort_keys=True)
                if all(json.dumps(row, ensure_ascii=False, sort_keys=True) != key for row in rows):
                    rows.append(provenance)
                result.append(destination)

        if not result:
            warnings.append(f"No PPTX found in ZIP: {path}")
        return result

    def _process_pptx(self, source, digest: str) -> dict:
        record = super()._process_pptx(source, digest)
        source_document_id = self._logical_document_fingerprint(record)
        archive_rows = list(self._archive_provenance_by_pptx_sha.get(digest, ()))
        if archive_rows:
            source_provenance = archive_rows
        else:
            source_provenance = [
                {
                    "source_kind": "direct-pptx",
                    "source_file": str(Path(source).resolve()),
                    "source_pptx_sha256": digest,
                }
            ]

        record["source_document_id"] = source_document_id
        record["source_provenance"] = source_provenance
        record["precision_trainer_version"] = PRECISION_TRAINER_VERSION
        for item in record.get("evidence", []):
            if not isinstance(item, dict):
                continue
            metadata = dict(item.get("metadata", {}) or {})
            metadata["source_document_id"] = source_document_id
            metadata["source_sha256"] = digest
            metadata["source_provenance"] = source_provenance
            item["metadata"] = metadata
        return record

    def _finalize_report(self, report: CorpusTrainingReport) -> CorpusTrainingReport:
        """Persist archive lineage on learned canonical assets without changing identity."""
        if not hasattr(self.library, "all") or not hasattr(self.library, "update_metadata"):
            return report

        provenance_by_sha: dict[str, list[dict[str, Any]]] = {}
        for decision in report.decisions:
            rows: list[dict[str, Any]] = []
            seen: set[str] = set()
            for evidence in decision.evidence:
                source_rows = (evidence.metadata or {}).get("source_provenance", ())
                if isinstance(source_rows, dict):
                    source_rows = (source_rows,)
                for row in source_rows or ():
                    if not isinstance(row, dict):
                        continue
                    key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(dict(row))
            if rows:
                provenance_by_sha[decision.image_sha256] = rows

        if not provenance_by_sha:
            return report

        try:
            assets = list(self.library.all())
        except Exception as exc:
            report.warnings.append(f"Archive provenance enrichment skipped: {exc}")
            return report

        for asset in assets:
            metadata = dict(getattr(asset, "metadata", {}) or {})
            canonical_sha = str(metadata.get("sha256_full") or metadata.get("sha256") or "").lower()
            variant_sha = {str(value).lower() for value in metadata.get("variant_sha256", ()) if value}
            matching_sha = next(
                (
                    digest
                    for digest in provenance_by_sha
                    if digest == canonical_sha
                    or digest in variant_sha
                    or str(getattr(asset, "id", "")) == digest[:24]
                ),
                "",
            )
            if not matching_sha:
                continue

            current = metadata.get("source_provenance")
            if isinstance(current, dict):
                current_rows = [current]
            elif isinstance(current, (list, tuple)):
                current_rows = [row for row in current if isinstance(row, dict)]
            else:
                current_rows = []
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for row in [*current_rows, *provenance_by_sha[matching_sha]]:
                key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(dict(row))
            if merged == current_rows:
                continue
            try:
                self.library.update_metadata(asset.id, metadata={"source_provenance": merged})
            except Exception as exc:
                report.warnings.append(f"Could not persist archive provenance for {asset.id}: {exc}")
        report.warnings = list(dict.fromkeys(report.warnings))
        return report

    @staticmethod
    def _logical_document_fingerprint(record: dict) -> str:
        # Product/image pairs are more stable across Canva/PowerPoint export copies
        # than package-level bytes or relationship IDs. Bboxes and archive paths are
        # intentionally excluded so harmless export/copy changes cannot manufacture
        # a new independent source.
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
            # never enough by itself to cross the automatic approval gate.
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
