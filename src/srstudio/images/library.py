from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image


SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


@dataclass(slots=True)
class ImageAsset:
    id: str
    path: str
    original_name: str
    width: int
    height: int
    mode: str
    bytes_size: int
    imported_at: str
    product_key: str = ""
    tags: tuple[str, ...] = ()
    product_name: str = ""
    aliases: tuple[str, ...] = ()
    kind: str = "unknown"
    confidence: float = 0.0
    review_status: str = "pending"
    source: str = "manual"
    source_file: str = ""
    slide_index: int = 0
    perceptual_hash: str = ""
    preferred: bool = False
    usage_count: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def megapixels(self) -> float:
        return round((self.width * self.height) / 1_000_000, 2)


@dataclass(frozen=True, slots=True)
class ImageMatch:
    asset: ImageAsset
    score: float
    reason: str


class ImageLibrary:
    """Persistent SR product-image bank with dedupe, review and fuzzy matching."""

    AUTO_ACCEPT_CONFIDENCE = 0.82
    AUTO_MATCH_SCORE = 0.67

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.assets_dir = self.root / "assets"
        self.index_path = self.root / "index.json"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def import_image(
        self,
        source: str | Path,
        product_key: str = "",
        tags: tuple[str, ...] = (),
        *,
        product_name: str = "",
        aliases: tuple[str, ...] = (),
        kind: str = "unknown",
        confidence: float = 0.0,
        review_status: str = "pending",
        source_kind: str = "manual",
        source_file: str = "",
        slide_index: int = 0,
        preferred: bool = False,
        metadata: dict | None = None,
    ) -> ImageAsset:
        source = Path(source)
        if source.suffix.lower() not in SUPPORTED:
            raise ValueError(f"Formato de imagem não suportado: {source.suffix}")
        digest = self._hash(source)
        target = self.assets_dir / f"{digest}{source.suffix.lower()}"
        if not target.exists():
            shutil.copy2(source, target)
        with Image.open(target) as image:
            width, height = image.size
            mode = image.mode
            perceptual_hash = self._dhash(image)

        normalized_key = self.normalize_product_key(product_key or product_name)
        index = self._load()
        existing_data = index.get(digest)
        if existing_data:
            existing = self._asset(existing_data)
            asset = self._merge_asset(
                existing,
                product_key=normalized_key,
                product_name=product_name,
                aliases=aliases,
                tags=tags,
                kind=kind,
                confidence=confidence,
                review_status=review_status,
                source=source_kind,
                source_file=source_file,
                slide_index=slide_index,
                preferred=preferred,
                metadata=metadata or {},
            )
        else:
            asset = ImageAsset(
                id=digest,
                path=str(target),
                original_name=source.name,
                width=width,
                height=height,
                mode=mode,
                bytes_size=target.stat().st_size,
                imported_at=datetime.now().isoformat(timespec="seconds"),
                product_key=normalized_key,
                tags=tuple(sorted(set(tags))),
                product_name=product_name.strip(),
                aliases=tuple(sorted({alias.strip() for alias in aliases if alias.strip()})),
                kind=kind,
                confidence=max(0.0, min(1.0, float(confidence))),
                review_status=review_status,
                source=source_kind,
                source_file=source_file,
                slide_index=int(slide_index or 0),
                perceptual_hash=perceptual_hash,
                preferred=bool(preferred),
                metadata=dict(metadata or {}),
            )
        index[digest] = asdict(asset)
        self._save(index)
        return asset

    def learn_product_image(
        self,
        source: str | Path,
        product_name: str,
        *,
        confidence: float,
        source_file: str = "",
        slide_index: int = 0,
        aliases: tuple[str, ...] = (),
        metadata: dict | None = None,
    ) -> ImageAsset:
        product_key = self.normalize_product_key(product_name)
        near = self.find_near_duplicate(source, product_key)
        status = "accepted" if confidence >= self.AUTO_ACCEPT_CONFIDENCE else "pending"
        if near is not None:
            return self.update_metadata(
                near.id,
                product_name=product_name,
                aliases=aliases,
                confidence=max(near.confidence, confidence),
                review_status="accepted" if near.review_status == "accepted" or status == "accepted" else "pending",
                source_file=source_file or near.source_file,
                slide_index=slide_index or near.slide_index,
                metadata={**near.metadata, **(metadata or {})},
            )
        return self.import_image(
            source,
            product_key=product_key,
            product_name=product_name,
            aliases=aliases,
            kind="product",
            confidence=confidence,
            review_status=status,
            source_kind="canva",
            source_file=source_file,
            slide_index=slide_index,
            tags=("canva", "produto"),
            metadata=metadata,
        )

    def find_for_product(self, product_key: str) -> list[ImageAsset]:
        key = self.normalize_product_key(product_key)
        if not key:
            return []
        assets = [
            self._asset(data)
            for data in self._load().values()
            if self.normalize_product_key(str(data.get("product_key") or data.get("product_name") or "")) == key
            and data.get("review_status", "pending") != "rejected"
        ]
        return sorted(assets, key=self._rank_asset, reverse=True)

    def find_best_for_product(self, product_name: str, aliases: tuple[str, ...] = ()) -> ImageMatch | None:
        query = self.normalize_product_key(product_name)
        if not query:
            return None
        query_tokens = set(query.split())
        candidates: list[ImageMatch] = []
        for data in self._load().values():
            asset = self._asset(data)
            if asset.kind not in {"product", "unknown"} or asset.review_status == "rejected":
                continue
            names = [asset.product_key, asset.product_name, *asset.aliases]
            best_text = 0.0
            reason = "similaridade"
            for name in names:
                normalized = self.normalize_product_key(name)
                if not normalized:
                    continue
                if normalized == query:
                    best_text = 1.0
                    reason = "nome exato"
                    break
                tokens = set(normalized.split())
                union = query_tokens | tokens
                jaccard = len(query_tokens & tokens) / max(len(union), 1)
                sequence = SequenceMatcher(None, query, normalized).ratio()
                score = max(jaccard * 0.72 + sequence * 0.28, sequence * 0.82)
                if score > best_text:
                    best_text = score
            for alias in aliases:
                if self.normalize_product_key(alias) == self.normalize_product_key(asset.product_name):
                    best_text = max(best_text, 0.94)
                    reason = "alias"
            if best_text < 0.48:
                continue
            trust = 0.0
            if asset.review_status == "accepted":
                trust += 0.08
            if asset.preferred:
                trust += 0.08
            trust += min(0.08, asset.confidence * 0.08)
            quality = min(0.04, asset.megapixels / 10.0)
            candidates.append(ImageMatch(asset, min(1.0, best_text + trust + quality), reason))
        if not candidates:
            return None
        best = max(candidates, key=lambda item: item.score)
        return best if best.score >= self.AUTO_MATCH_SCORE else None

    def find_near_duplicate(self, source: str | Path, product_key: str = "", max_distance: int = 6) -> ImageAsset | None:
        path = Path(source)
        try:
            with Image.open(path) as image:
                fingerprint = self._dhash(image)
        except (OSError, ValueError):
            return None
        normalized_key = self.normalize_product_key(product_key)
        for data in self._load().values():
            asset = self._asset(data)
            if normalized_key and asset.product_key and self.normalize_product_key(asset.product_key) != normalized_key:
                continue
            if asset.perceptual_hash and self._hamming_hex(fingerprint, asset.perceptual_hash) <= max_distance:
                return asset
        return None

    def update_metadata(self, asset_id: str, **changes) -> ImageAsset:
        index = self._load()
        if asset_id not in index:
            raise KeyError(asset_id)
        asset = self._asset(index[asset_id])
        data = asdict(asset)
        for key, value in changes.items():
            if key not in data:
                continue
            if key in {"aliases", "tags"}:
                value = tuple(value or ())
            if key == "product_key":
                value = self.normalize_product_key(str(value or ""))
            data[key] = value
        updated = self._asset(data)
        index[asset_id] = asdict(updated)
        self._save(index)
        return updated

    def set_review_status(self, asset_id: str, status: str) -> ImageAsset:
        if status not in {"accepted", "pending", "rejected"}:
            raise ValueError(status)
        return self.update_metadata(asset_id, review_status=status)

    def set_preferred(self, asset_id: str, preferred: bool = True) -> ImageAsset:
        index = self._load()
        target = self._asset(index[asset_id])
        if preferred and target.product_key:
            for key, data in list(index.items()):
                asset = self._asset(data)
                if asset.product_key == target.product_key and asset.preferred:
                    asset.preferred = False
                    index[key] = asdict(asset)
        target.preferred = preferred
        index[asset_id] = asdict(target)
        self._save(index)
        return target

    def record_use(self, asset_id: str) -> None:
        index = self._load()
        if asset_id not in index:
            return
        asset = self._asset(index[asset_id])
        asset.usage_count += 1
        index[asset_id] = asdict(asset)
        self._save(index)

    def all(self, *, kind: str = "", status: str = "") -> list[ImageAsset]:
        assets = [self._asset(data) for data in self._load().values()]
        if kind:
            assets = [asset for asset in assets if asset.kind == kind]
        if status:
            assets = [asset for asset in assets if asset.review_status == status]
        return sorted(assets, key=lambda item: item.imported_at, reverse=True)

    def pending_review(self) -> list[ImageAsset]:
        return self.all(status="pending")

    def search(self, query: str, limit: int = 100) -> list[ImageAsset]:
        normalized = self.normalize_product_key(query)
        if not normalized:
            return self.all()[:limit]
        scored: list[tuple[float, ImageAsset]] = []
        for asset in self.all():
            haystack = " ".join((asset.product_key, asset.product_name, *asset.aliases, *asset.tags))
            value = self.normalize_product_key(haystack)
            if normalized in value:
                scored.append((1.0, asset))
            else:
                score = SequenceMatcher(None, normalized, value).ratio()
                if score >= 0.35:
                    scored.append((score, asset))
        return [asset for _, asset in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]

    def duplicate_groups(self) -> list[list[ImageAsset]]:
        groups: dict[str, list[ImageAsset]] = {}
        for asset in self.all(kind="product"):
            key = asset.product_key or self.normalize_product_key(asset.product_name)
            if key:
                groups.setdefault(key, []).append(asset)
        return [sorted(items, key=self._rank_asset, reverse=True) for items in groups.values() if len(items) > 1]

    def stats(self) -> dict[str, int]:
        assets = self.all()
        return {
            "total": len(assets),
            "products": sum(asset.kind == "product" for asset in assets),
            "accepted": sum(asset.review_status == "accepted" for asset in assets),
            "pending": sum(asset.review_status == "pending" for asset in assets),
            "rejected": sum(asset.review_status == "rejected" for asset in assets),
            "duplicates": sum(max(0, len(group) - 1) for group in self.duplicate_groups()),
        }

    def quality_warnings(self, asset: ImageAsset, target_width_px: int, target_height_px: int) -> list[str]:
        warnings: list[str] = []
        if asset.width < target_width_px or asset.height < target_height_px:
            warnings.append("Imagem possui resolução menor que a área de destino.")
        if asset.megapixels < 0.25:
            warnings.append("Imagem de resolução muito baixa para impressão de alta qualidade.")
        ratio_asset = asset.width / max(asset.height, 1)
        ratio_target = target_width_px / max(target_height_px, 1)
        if abs(ratio_asset - ratio_target) > 1.0:
            warnings.append("Proporção da imagem é muito diferente da caixa de destino; poderá exigir recorte.")
        return warnings

    def _load(self) -> dict:
        if not self.index_path.exists():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _save(self, payload: dict) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    @staticmethod
    def normalize_product_key(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(character for character in text if not unicodedata.combining(character))
        text = text.upper().replace("Ç", "C")
        text = re.sub(r"[^A-Z0-9]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _hash(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:24]

    @staticmethod
    def _dhash(image: Image.Image) -> str:
        gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
        value = 0
        bit = 0
        for row in range(8):
            offset = row * 9
            for column in range(8):
                if pixels[offset + column] > pixels[offset + column + 1]:
                    value |= 1 << bit
                bit += 1
        return f"{value:016x}"

    @staticmethod
    def _hamming_hex(left: str, right: str) -> int:
        try:
            return (int(left, 16) ^ int(right, 16)).bit_count()
        except (TypeError, ValueError):
            return 64

    @staticmethod
    def _rank_asset(asset: ImageAsset) -> tuple:
        return (
            asset.preferred,
            asset.review_status == "accepted",
            asset.confidence,
            asset.usage_count,
            asset.width * asset.height,
        )

    @staticmethod
    def _merge_asset(
        existing: ImageAsset,
        *,
        product_key: str,
        product_name: str,
        aliases: tuple[str, ...],
        tags: tuple[str, ...],
        kind: str,
        confidence: float,
        review_status: str,
        source: str,
        source_file: str,
        slide_index: int,
        preferred: bool,
        metadata: dict,
    ) -> ImageAsset:
        names = set(existing.aliases)
        if existing.product_name and product_name and existing.product_name != product_name:
            names.add(product_name)
        names.update(alias for alias in aliases if alias)
        existing.aliases = tuple(sorted(names))
        existing.tags = tuple(sorted(set(existing.tags) | set(tags)))
        existing.product_key = existing.product_key or product_key
        existing.product_name = existing.product_name or product_name
        if existing.kind == "unknown" and kind:
            existing.kind = kind
        existing.confidence = max(existing.confidence, max(0.0, min(1.0, float(confidence))))
        if review_status == "accepted" or existing.review_status != "accepted":
            existing.review_status = review_status or existing.review_status
        existing.source = existing.source or source
        existing.source_file = existing.source_file or source_file
        existing.slide_index = existing.slide_index or int(slide_index or 0)
        existing.preferred = existing.preferred or bool(preferred)
        existing.metadata = {**existing.metadata, **metadata}
        return existing

    @staticmethod
    def _asset(data: dict) -> ImageAsset:
        data = dict(data)
        defaults = {
            "product_key": "",
            "tags": (),
            "product_name": "",
            "aliases": (),
            "kind": "unknown",
            "confidence": 0.0,
            "review_status": "pending",
            "source": "manual",
            "source_file": "",
            "slide_index": 0,
            "perceptual_hash": "",
            "preferred": False,
            "usage_count": 0,
            "metadata": {},
        }
        for key, value in defaults.items():
            data.setdefault(key, value)
        data["tags"] = tuple(data.get("tags") or ())
        data["aliases"] = tuple(data.get("aliases") or ())
        data["metadata"] = dict(data.get("metadata") or {})
        return ImageAsset(**data)
