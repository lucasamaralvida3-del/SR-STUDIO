from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from srstudio.images.association import (
    is_product_text_candidate,
    measurement_signature,
    normalize_product_name,
    product_name_similarity,
    product_names_compatible,
)


_GENERATED_SUFFIX_RE = re.compile(r"\s*[-_ ](?:COPY|COPIA|EDITADO|EDITED|FINAL|NOVO|NOVA|SEM FUNDO)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class StandaloneImageSource:
    path: str
    label: str = ""
    product_name: str = ""
    verified: bool = False
    provenance: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StandaloneMatch:
    path: str
    product_name: str
    normalized_name: str
    confidence: float
    status: str
    reason: str
    alternatives: tuple[str, ...] = ()
    image_id: str = ""


@dataclass(frozen=True, slots=True)
class StandaloneTrainingReport:
    discovered: int
    accepted: int
    review: int
    unknown: int
    imported: int
    matches: tuple[StandaloneMatch, ...]
    warnings: tuple[str, ...] = ()


class StandaloneProductImageTrainer:
    """Precision-first ingestion for product images that do not come from PPTX.

    Standalone filenames/titles are evidence, not ground truth. Verified manifest
    mappings can auto-accept. An exact normalized match to a known catalog product
    can also auto-accept; strong fuzzy matches remain pending so packaging variants,
    flavours and gramatures are never silently collapsed.
    """

    def __init__(self, library, catalog_names: Iterable[str] = ()) -> None:
        self.library = library
        self.catalog = self._catalog(catalog_names)

    def train(self, sources: Iterable[StandaloneImageSource]) -> StandaloneTrainingReport:
        rows = list(sources)
        matches: list[StandaloneMatch] = []
        warnings: list[str] = []
        accepted = review = unknown = imported = 0

        for source in rows:
            path = Path(source.path)
            if not path.is_file():
                warnings.append(f"Standalone image not found: {path}")
                matches.append(
                    StandaloneMatch(str(path), "", "", 0.0, "unknown", "missing-file")
                )
                unknown += 1
                continue

            match = self.match(source)
            if match.status == "unknown":
                unknown += 1
                matches.append(match)
                continue

            confidence = match.confidence
            if match.status != "accepted":
                library_gate = float(getattr(self.library, "AUTO_ACCEPT_CONFIDENCE", 0.82))
                confidence = min(confidence, max(0.0, library_gate - 0.001))

            metadata = {
                "standalone": True,
                "association_status": match.status,
                "association_confidence": match.confidence,
                "match_reason": match.reason,
                "source_label": source.label,
                "verified_mapping": bool(source.verified),
                "alternatives": list(match.alternatives),
                "provenance": [
                    {
                        "source_kind": "standalone-library",
                        "source_file": path.name,
                        "source_path": str(path),
                        **dict(source.provenance or {}),
                    }
                ],
            }
            asset = self.library.learn_product_image(
                path,
                match.product_name,
                confidence=confidence,
                source_file=path.name,
                metadata=metadata,
            )
            changes = {
                "source": "standalone-library",
                "metadata": metadata,
                "confidence": match.confidence,
            }
            if match.status != "accepted":
                changes["review_status"] = "pending"
            asset = self.library.update_metadata(asset.id, **changes)
            imported += 1
            if match.status == "accepted":
                accepted += 1
            else:
                review += 1
            matches.append(
                StandaloneMatch(
                    path=match.path,
                    product_name=match.product_name,
                    normalized_name=match.normalized_name,
                    confidence=match.confidence,
                    status=match.status,
                    reason=match.reason,
                    alternatives=match.alternatives,
                    image_id=asset.id,
                )
            )

        return StandaloneTrainingReport(
            discovered=len(rows),
            accepted=accepted,
            review=review,
            unknown=unknown,
            imported=imported,
            matches=tuple(matches),
            warnings=tuple(warnings),
        )

    def match(self, source: StandaloneImageSource) -> StandaloneMatch:
        path = Path(source.path)
        explicit = " ".join(str(source.product_name or "").split())
        label = " ".join(str(source.label or "").split()) or self._label_from_filename(path)

        if source.verified and explicit:
            return StandaloneMatch(
                str(path),
                explicit,
                normalize_product_name(explicit),
                0.99,
                "accepted",
                "verified-manifest",
            )

        query = explicit or label
        normalized_query = normalize_product_name(query)
        if not normalized_query or not is_product_text_candidate(query):
            return StandaloneMatch(str(path), "", normalized_query, 0.0, "unknown", "not-product-like")

        if not self.catalog:
            if explicit:
                return StandaloneMatch(
                    str(path), explicit, normalized_query, 0.78, "review", "explicit-without-catalog"
                )
            return StandaloneMatch(str(path), "", normalized_query, 0.0, "unknown", "catalog-required")

        ranked: list[tuple[float, str, str]] = []
        for normalized_catalog, display_name in self.catalog.items():
            if not self._measurement_compatible(normalized_query, normalized_catalog):
                continue
            score = 1.0 if normalized_query == normalized_catalog else product_name_similarity(query, display_name)
            if score >= 0.58:
                ranked.append((score, display_name, normalized_catalog))
        ranked.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
        if not ranked:
            return StandaloneMatch(str(path), "", normalized_query, 0.0, "unknown", "no-catalog-match")

        best_score, best_name, best_normalized = ranked[0]
        alternatives = tuple(name for _, name, _ in ranked[1:4])
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0
        margin = best_score - second_score

        if normalized_query == best_normalized:
            return StandaloneMatch(
                str(path), best_name, best_normalized, 0.92, "accepted", "exact-catalog-name", alternatives
            )

        # Strong fuzzy evidence still goes to review. This is intentional: a title
        # such as TODDY 370G must never be promoted to TODDY 750G just because the
        # package looks/name reads similarly.
        if best_score >= 0.94 and margin >= 0.08 and product_names_compatible(query, best_name):
            return StandaloneMatch(
                str(path), best_name, best_normalized, 0.81, "review", "strong-catalog-fuzzy", alternatives
            )
        if best_score >= 0.82 and margin >= 0.10:
            return StandaloneMatch(
                str(path), best_name, best_normalized, 0.72, "review", "catalog-fuzzy", alternatives
            )
        return StandaloneMatch(
            str(path), best_name, best_normalized, min(0.69, best_score), "review", "ambiguous-catalog-match", alternatives
        )

    @staticmethod
    def _catalog(names: Iterable[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in names:
            display = " ".join(str(name or "").split())
            normalized = normalize_product_name(display)
            if display and normalized:
                result.setdefault(normalized, display)
        return result

    @staticmethod
    def _measurement_compatible(left: str, right: str) -> bool:
        left_signature = measurement_signature(left)
        right_signature = measurement_signature(right)
        if left_signature and right_signature and left_signature != right_signature:
            return False
        return True

    @staticmethod
    def _label_from_filename(path: Path) -> str:
        text = path.stem.replace("_", " ").replace("-", " ")
        text = _GENERATED_SUFFIX_RE.sub("", text)
        return " ".join(text.split())


def load_manifest(path: str | Path) -> list[StandaloneImageSource]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("images", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Standalone image manifest must be a list or {'images': [...]} object")
    result: list[StandaloneImageSource] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("path"):
            continue
        result.append(
            StandaloneImageSource(
                path=str(row["path"]),
                label=str(row.get("label", "")),
                product_name=str(row.get("product_name", "")),
                verified=bool(row.get("verified", False)),
                provenance=dict(row.get("provenance", {}) or {}),
            )
        )
    return result
