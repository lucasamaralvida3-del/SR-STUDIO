from __future__ import annotations

from typing import Any

from srstudio.images.association import AssociationEvidence, spatial_pair_score
from srstudio.images.corpus_training import ProductImageCorpusTrainer, _ImageCandidate, _PRICE_TEXT_RE


class PrecisionProductImageCorpusTrainer(ProductImageCorpusTrainer):
    """Precision-first pairing policy for the real Canva/PPTX corpus.

    Canva commonly repeats the same embedded media in two or more shape fills on
    one slide. Those shapes are a single logical image and must not compete with
    each other. A one-product/one-logical-image slide is also useful evidence even
    when Canva's transparent shape bbox makes the geometric score weak; in that
    special case the observation is retained but capped below auto-accept.
    """

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
