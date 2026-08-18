from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

from srstudio.images.library import ImageAsset, ImageLibrary
from srstudio.images.perceptual_index import HammingPerceptualIndex, PerceptualIndexEntry
from srstudio.images.quality import ImageQualityAnalyzer
from srstudio.images.visual_dedup import compact_rgb_signature, is_conservative_visual_duplicate


class ImageLibraryCorruptionError(RuntimeError):
    """Raised when the persisted image index cannot be trusted."""


class SafeImageLibrary(ImageLibrary):
    """ImageLibrary with fail-closed persistence and conservative visual dedupe.

    The original library API is intentionally preserved. Persistence is hardened:
    existing JSON is validated before writes, a rolling logical backup is made,
    the replacement is validated, then atomically installed. Perceptual duplicate
    checks use a metadata-only BK-tree to find nearby dHash candidates and then
    require compatible geometry plus coarse RGB content before merging.

    New imports also persist a lightweight product-image quality assessment once.
    Interactive lookup can rank variants from metadata without reopening thousands
    of image files.
    """

    @property
    def backup_path(self) -> Path:
        return self.index_path.with_suffix(self.index_path.suffix + ".bak")

    def import_image(self, source: str | Path, *args, metadata: dict | None = None, **kwargs) -> ImageAsset:
        source_path = Path(source)
        full_sha256 = self._full_sha256(source_path)
        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("sha256_full", full_sha256)
        merged_metadata.setdefault("sha256", full_sha256)
        rgb_signature = self._rgb_signature_for_path(source_path)
        if rgb_signature:
            merged_metadata.setdefault("rgb_signature", rgb_signature)

        if "quality_score" not in merged_metadata:
            try:
                quality = ImageQualityAnalyzer().product_quality(source_path, metadata=merged_metadata).metadata()
                for key, value in quality.items():
                    merged_metadata.setdefault(key, value)
            except (OSError, ValueError):
                # A corrupt/unsupported raster will still fail in the base importer;
                # quality analysis itself must not manufacture a different failure.
                pass

        # Exact duplicates use the legacy 24-hex asset id. Merge provenance before
        # delegating so repeated observations cannot erase earlier source records.
        legacy_id = ImageLibrary._hash(source_path)
        current_data = self._load().get(legacy_id)
        if current_data:
            current = self._asset(current_data)
            merged_metadata = self._merge_provenance_metadata(
                current.metadata,
                merged_metadata,
                canonical_sha256=self._canonical_sha256(current),
            )
        return super().import_image(source, *args, metadata=merged_metadata, **kwargs)

    def update_metadata(self, asset_id: str, **changes) -> ImageAsset:
        if "metadata" not in changes:
            return super().update_metadata(asset_id, **changes)

        index = self._load()
        if asset_id not in index:
            raise KeyError(asset_id)
        current = self._asset(index[asset_id])
        incoming = dict(changes.get("metadata") or {})
        changes["metadata"] = self._merge_provenance_metadata(
            current.metadata,
            incoming,
            canonical_sha256=self._canonical_sha256(current),
        )
        return super().update_metadata(asset_id, **changes)

    def _load(self) -> dict:
        if not self.index_path.exists():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ImageLibraryCorruptionError(
                f"Image library index is invalid and was not reset: {self.index_path}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ImageLibraryCorruptionError(
                f"Image library index must be a JSON object: {self.index_path}"
            )
        return payload

    def _save(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            raise TypeError("Image library payload must be a dictionary")
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        if self.index_path.exists():
            self._load()
            shutil.copy2(self.index_path, self.backup_path)

        tmp = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            check = json.loads(tmp.read_text(encoding="utf-8"))
            if not isinstance(check, dict):
                raise ImageLibraryCorruptionError("Temporary image index is not a JSON object")
            tmp.replace(self.index_path)
            self._invalidate_perceptual_cache()
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _canonical_sha256(self, asset: ImageAsset) -> str:
        metadata = dict(asset.metadata or {})
        canonical = str(metadata.get("sha256_full") or metadata.get("sha256") or "").strip().lower()
        if len(canonical) == 64:
            return canonical
        try:
            return self._full_sha256(Path(asset.path))
        except OSError:
            return canonical

    @classmethod
    def _merge_provenance_metadata(
        cls,
        current: dict | None,
        incoming: dict | None,
        *,
        canonical_sha256: str,
    ) -> dict:
        current = dict(current or {})
        incoming = dict(incoming or {})
        merged = {**current, **incoming}

        incoming_sha = str(incoming.get("sha256_full") or incoming.get("sha256") or "").strip().lower()
        variants = {
            str(value).strip().lower()
            for value in (
                *(current.get("variant_sha256") or ()),
                *(incoming.get("variant_sha256") or ()),
            )
            if str(value).strip()
        }
        if incoming_sha and canonical_sha256 and incoming_sha != canonical_sha256:
            variants.add(incoming_sha)
        if canonical_sha256:
            merged["sha256"] = canonical_sha256
            merged["sha256_full"] = canonical_sha256
        if variants:
            variants.discard(canonical_sha256)
            merged["variant_sha256"] = sorted(variants)

        # Canonical visual/quality metadata must not be overwritten by a later
        # recompressed near-duplicate merely because its provenance is merged.
        for key in (
            "rgb_signature",
            "quality_score",
            "resolution_score",
            "transparency_score",
            "sharpness_score",
            "border_cleanliness_score",
            "transparent_ratio",
            "edge_stddev",
            "border_stddev",
            "penalties",
        ):
            if key in current:
                merged[key] = current[key]

        provenance = cls._merge_provenance_lists(
            current.get("provenance"),
            incoming.get("provenance"),
        )
        if provenance:
            merged["provenance"] = provenance
        source_provenance = cls._merge_provenance_lists(
            current.get("source_provenance"),
            incoming.get("source_provenance"),
        )
        if source_provenance:
            merged["source_provenance"] = source_provenance
        return merged

    @staticmethod
    def _merge_provenance_lists(*values) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for value in values:
            if isinstance(value, dict):
                rows = [value]
            elif isinstance(value, (list, tuple)):
                rows = value
            else:
                rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                result.append(dict(row))
        return result

    @staticmethod
    def _full_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _rgb_signature_for_path(path: Path) -> str:
        try:
            with Image.open(path) as image:
                return compact_rgb_signature(image)
        except (OSError, ValueError):
            return ""

    @staticmethod
    def _source_visual_signature(source: str | Path) -> tuple[str, tuple[int, int], str] | None:
        path = Path(source)
        try:
            with Image.open(path) as image:
                return ImageLibrary._dhash(image), image.size, compact_rgb_signature(image)
        except (OSError, ValueError):
            return None

    @classmethod
    def _asset_rgb_signature(cls, asset: ImageAsset) -> str:
        signature = str((asset.metadata or {}).get("rgb_signature") or "")
        if signature:
            return signature
        return cls._rgb_signature_for_path(Path(asset.path))

    @classmethod
    def _is_visual_duplicate(
        cls,
        fingerprint: str,
        source_size: tuple[int, int],
        source_rgb_signature: str,
        asset: ImageAsset,
        max_distance: int,
    ) -> bool:
        return bool(
            asset.perceptual_hash
            and is_conservative_visual_duplicate(
                fingerprint,
                asset.perceptual_hash,
                source_size,
                (asset.width, asset.height),
                left_rgb_signature=source_rgb_signature,
                right_rgb_signature=cls._asset_rgb_signature(asset),
                max_hamming_distance=max_distance,
            )
        )

    def _invalidate_perceptual_cache(self) -> None:
        self.__dict__.pop("_perceptual_cache_signature", None)
        self.__dict__.pop("_perceptual_cache_index", None)
        self.__dict__.pop("_perceptual_cache_payload", None)

    def _perceptual_snapshot(self) -> tuple[HammingPerceptualIndex, dict]:
        try:
            stat = self.index_path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            signature = None

        cached_signature = self.__dict__.get("_perceptual_cache_signature")
        cached_index = self.__dict__.get("_perceptual_cache_index")
        cached_payload = self.__dict__.get("_perceptual_cache_payload")
        if cached_index is not None and cached_payload is not None and cached_signature == signature:
            return cached_index, cached_payload

        payload = self._load()
        entries = [
            PerceptualIndexEntry(asset_id=str(asset_id), perceptual_hash=str(data.get("perceptual_hash") or ""))
            for asset_id, data in payload.items()
            if isinstance(data, dict) and data.get("perceptual_hash")
        ]
        index = HammingPerceptualIndex(entries)
        self.__dict__["_perceptual_cache_signature"] = signature
        self.__dict__["_perceptual_cache_index"] = index
        self.__dict__["_perceptual_cache_payload"] = payload
        return index, payload

    def _perceptual_candidates(self, fingerprint: str, max_distance: int) -> list[ImageAsset]:
        index, payload = self._perceptual_snapshot()
        result: list[ImageAsset] = []
        for _, entry in index.search(fingerprint, max_distance):
            data = payload.get(entry.asset_id)
            if isinstance(data, dict):
                result.append(self._asset(data))
        return result

    def find_near_duplicate(
        self,
        source: str | Path,
        product_key: str = "",
        max_distance: int = ImageLibrary.VISUAL_DUPLICATE_DISTANCE,
    ) -> ImageAsset | None:
        signature = self._source_visual_signature(source)
        if signature is None:
            return None
        fingerprint, source_size, source_rgb_signature = signature
        normalized_key = self.normalize_product_key(product_key)
        for asset in self._perceptual_candidates(fingerprint, max_distance):
            if normalized_key and asset.product_key and self.normalize_product_key(asset.product_key) != normalized_key:
                continue
            if self._is_visual_duplicate(fingerprint, source_size, source_rgb_signature, asset, max_distance):
                return asset
        return None

    def find_cross_product_visual_duplicate(
        self,
        source: str | Path,
        product_key: str,
        max_distance: int = ImageLibrary.VISUAL_DUPLICATE_DISTANCE,
    ) -> ImageAsset | None:
        signature = self._source_visual_signature(source)
        if signature is None:
            return None
        fingerprint, source_size, source_rgb_signature = signature
        normalized_key = self.normalize_product_key(product_key)
        if not normalized_key:
            return None
        for asset in self._perceptual_candidates(fingerprint, max_distance):
            asset_key = self.normalize_product_key(asset.product_key or asset.product_name)
            if not asset_key or asset_key == normalized_key:
                continue
            if self._is_visual_duplicate(fingerprint, source_size, source_rgb_signature, asset, max_distance):
                return asset
        return None
