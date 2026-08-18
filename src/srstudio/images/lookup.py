from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from srstudio.images.association import measurement_signature, normalize_product_name, product_name_similarity
from srstudio.images.quality import asset_quality_score


@dataclass(frozen=True, slots=True)
class ProductImageCandidate:
    asset: Any
    score: float
    reason: str
    match_type: str = ""
    quality_score: float = 0.0
    identity_score: float = 0.0
    provenance: tuple[dict, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductImageLookupResult:
    best_match: ProductImageCandidate | None
    alternatives: tuple[ProductImageCandidate, ...]
    confidence: float
    match_type: str = ""
    quality_score: float = 0.0
    provenance: tuple[dict, ...] = ()


class ProductImageLookupService:
    """Metadata-only interactive lookup facade for the product image bank.

    Product identity always outranks aesthetics. Visual quality is used only as a
    variant/tie-break signal after name/SKU compatibility has been established.
    """

    def __init__(
        self,
        library: Any,
        *,
        minimum_score: float = 0.67,
        max_fuzzy_candidates: int = 750,
    ) -> None:
        self.library = library
        self.minimum_score = float(minimum_score)
        self.max_fuzzy_candidates = max(50, int(max_fuzzy_candidates))
        self._assets: list[Any] = []
        self._exact: dict[str, list[Any]] = {}
        self._tokens: dict[str, set[int]] = {}
        self._stamp: tuple[int, int] | None = None

    def refresh(self) -> None:
        assets = [
            asset
            for asset in self.library.all(status="accepted")
            if getattr(asset, "kind", "unknown") in {"product", "unknown"}
        ]
        exact: dict[str, list[Any]] = {}
        tokens: dict[str, set[int]] = {}
        for index, asset in enumerate(assets):
            for name in self._asset_names(asset):
                normalized = normalize_product_name(name)
                if not normalized:
                    continue
                exact.setdefault(normalized, []).append(asset)
                for token in normalized.split():
                    if len(token) >= 2:
                        tokens.setdefault(token, set()).add(index)
        self._assets = assets
        self._exact = exact
        self._tokens = tokens
        self._stamp = self._index_stamp()

    def find_image(
        self,
        product_name: str,
        *,
        aliases: Iterable[str] = (),
        alternatives: int = 3,
    ) -> ProductImageLookupResult:
        self._ensure_fresh()
        query_names = [product_name, *[value for value in aliases if value]]
        normalized = normalize_product_name(product_name)
        if not normalized:
            return ProductImageLookupResult(None, (), 0.0)

        candidate_assets: dict[str, Any] = {}
        for query in query_names:
            q = normalize_product_name(query)
            for asset in self._exact.get(q, ()):
                candidate_assets[str(getattr(asset, "id", id(asset)))] = asset

        if not candidate_assets:
            token_sets = [
                (token, self._tokens[token])
                for token in normalized.split()
                if token in self._tokens
            ]
            token_sets.sort(key=lambda item: len(item[1]))
            candidate_ids: set[int] = set(token_sets[0][1]) if token_sets else set()

            # Start at the rarest query token and intersect with additional
            # evidence only when the intersection remains non-empty. This avoids
            # common tokens such as 500G or LEITE turning every fuzzy lookup into
            # a linear scan of the entire bank.
            for _, token_ids in token_sets[1:4]:
                intersection = candidate_ids & token_ids
                if intersection:
                    candidate_ids = intersection

            if len(candidate_ids) > self.max_fuzzy_candidates:
                rarity = {token: 1.0 / max(1, len(ids)) for token, ids in token_sets}
                candidate_ids = set(
                    sorted(
                        candidate_ids,
                        key=lambda index: sum(
                            rarity[token]
                            for token, ids in token_sets
                            if index in ids
                        ),
                        reverse=True,
                    )[: self.max_fuzzy_candidates]
                )

            for index in candidate_ids:
                asset = self._assets[index]
                candidate_assets[str(getattr(asset, "id", id(asset)))] = asset

        scored: list[ProductImageCandidate] = []
        query_signature = measurement_signature(product_name)
        for asset in candidate_assets.values():
            primary_names = tuple(
                value
                for value in (getattr(asset, "product_key", ""), getattr(asset, "product_name", ""))
                if value
            )
            alias_names = tuple(getattr(asset, "aliases", ()) or ())
            names = (*primary_names, *alias_names)
            best_text = 0.0
            match_type = "fuzzy"
            compatible_name = False
            for index, name in enumerate(names):
                if not name:
                    continue
                signature = measurement_signature(name)
                if query_signature and signature and query_signature != signature:
                    continue
                compatible_name = True
                normalized_name = normalize_product_name(name)
                if normalized_name == normalized:
                    best_text = 1.0
                    match_type = "exact-name" if index < len(primary_names) else "exact-alias"
                    break
                similarity = product_name_similarity(product_name, name)
                if similarity > best_text:
                    best_text = similarity
                    match_type = "fuzzy"
            if not compatible_name or best_text < 0.48:
                continue

            confidence = max(0.0, min(1.0, float(getattr(asset, "confidence", 0.0))))
            quality = asset_quality_score(asset)
            # Candidate score remains identity-dominant. Quality is a separate
            # sort field and cannot make a weaker SKU/name outrank a stronger one.
            score = min(1.0, best_text + 0.015 * confidence)
            reason = {
                "exact-name": "nome exato",
                "exact-alias": "alias exato",
                "fuzzy": "similaridade",
            }[match_type]
            scored.append(
                ProductImageCandidate(
                    asset=asset,
                    score=round(score, 6),
                    reason=reason,
                    match_type=match_type,
                    quality_score=quality,
                    identity_score=round(best_text, 6),
                    provenance=self._asset_provenance(asset),
                )
            )

        scored.sort(
            key=lambda item: (
                item.identity_score,
                bool(getattr(item.asset, "preferred", False)),
                float(getattr(item.asset, "confidence", 0.0)),
                item.quality_score,
                int(getattr(item.asset, "usage_count", 0)),
            ),
            reverse=True,
        )
        if not scored or scored[0].score < self.minimum_score:
            return ProductImageLookupResult(None, tuple(scored[: max(0, alternatives)]), 0.0)
        best = scored[0]
        return ProductImageLookupResult(
            best_match=best,
            alternatives=tuple(scored[1 : 1 + max(0, alternatives)]),
            confidence=best.score,
            match_type=best.match_type,
            quality_score=best.quality_score,
            provenance=best.provenance,
        )

    def _ensure_fresh(self) -> None:
        stamp = self._index_stamp()
        if self._stamp != stamp:
            self.refresh()

    def _index_stamp(self) -> tuple[int, int] | None:
        path = getattr(self.library, "index_path", None)
        if not path:
            return None if self._assets else (-1, -1)
        try:
            stat = Path(path).stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return (0, 0)

    @staticmethod
    def _asset_names(asset: Any) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                getattr(asset, "product_key", ""),
                getattr(asset, "product_name", ""),
                *(getattr(asset, "aliases", ()) or ()),
            )
            if value
        )

    @staticmethod
    def _asset_provenance(asset: Any) -> tuple[dict, ...]:
        metadata = dict(getattr(asset, "metadata", {}) or {})
        result: list[dict] = []
        seen: set[str] = set()
        for value in (metadata.get("source_provenance"), metadata.get("provenance")):
            if isinstance(value, dict):
                rows = (value,)
            elif isinstance(value, (list, tuple)):
                rows = value
            else:
                rows = ()
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = repr(sorted(row.items()))
                if key in seen:
                    continue
                seen.add(key)
                result.append(dict(row))
        return tuple(result)


def find_image(library: Any, product_name: str, *, alternatives: int = 3) -> ProductImageLookupResult:
    """One-shot compatibility facade for future ProductCard integration."""
    return ProductImageLookupService(library).find_image(product_name, alternatives=alternatives)
