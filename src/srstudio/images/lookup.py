from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from srstudio.images.association import measurement_signature, normalize_product_name, product_name_similarity


@dataclass(frozen=True, slots=True)
class ProductImageCandidate:
    asset: Any
    score: float
    reason: str


@dataclass(frozen=True, slots=True)
class ProductImageLookupResult:
    best_match: ProductImageCandidate | None
    alternatives: tuple[ProductImageCandidate, ...]
    confidence: float


class ProductImageLookupService:
    """Metadata-only interactive lookup facade for the product image bank."""

    def __init__(self, library: Any, *, minimum_score: float = 0.67) -> None:
        self.library = library
        self.minimum_score = float(minimum_score)
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
        exact_hit = False
        for query in query_names:
            q = normalize_product_name(query)
            for asset in self._exact.get(q, ()):
                candidate_assets[str(getattr(asset, "id", id(asset)))] = asset
                exact_hit = True
        if not candidate_assets:
            ids: set[int] = set()
            for token in normalized.split():
                ids.update(self._tokens.get(token, ()))
            for index in ids:
                asset = self._assets[index]
                candidate_assets[str(getattr(asset, "id", id(asset)))] = asset

        scored: list[ProductImageCandidate] = []
        query_signature = measurement_signature(product_name)
        for asset in candidate_assets.values():
            names = self._asset_names(asset)
            best_text = 0.0
            exact_name = False
            compatible_name = False
            for name in names:
                if not name:
                    continue
                signature = measurement_signature(name)
                if query_signature and signature and query_signature != signature:
                    continue
                compatible_name = True
                qn = normalize_product_name(name)
                if qn == normalized:
                    best_text = 1.0
                    exact_name = True
                    break
                best_text = max(best_text, product_name_similarity(product_name, name))
            if not compatible_name or best_text < 0.48:
                continue
            score = best_text
            score += 0.04 if bool(getattr(asset, "preferred", False)) else 0.0
            score += 0.04 * max(0.0, min(1.0, float(getattr(asset, "confidence", 0.0))))
            megapixels = float(getattr(asset, "megapixels", 0.0) or 0.0)
            score += min(0.02, megapixels / 25.0)
            score = min(1.0, score)
            reason = "nome exato" if exact_name else ("alias exato" if exact_hit else "similaridade")
            scored.append(ProductImageCandidate(asset, round(score, 6), reason))

        scored.sort(
            key=lambda item: (
                item.score,
                bool(getattr(item.asset, "preferred", False)),
                float(getattr(item.asset, "confidence", 0.0)),
                int(getattr(item.asset, "usage_count", 0)),
            ),
            reverse=True,
        )
        if not scored or scored[0].score < self.minimum_score:
            return ProductImageLookupResult(None, tuple(scored[: max(0, alternatives)]), 0.0)
        return ProductImageLookupResult(
            best_match=scored[0],
            alternatives=tuple(scored[1 : 1 + max(0, alternatives)]),
            confidence=scored[0].score,
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


def find_image(library: Any, product_name: str, *, alternatives: int = 3) -> ProductImageLookupResult:
    """One-shot compatibility facade for future ProductCard integration."""
    return ProductImageLookupService(library).find_image(product_name, alternatives=alternatives)
