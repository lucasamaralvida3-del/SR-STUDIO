from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

from srstudio.images.library import ImageAsset, ImageLibrary
from srstudio.images.visual_dedup import is_conservative_visual_duplicate


class ImageLibraryCorruptionError(RuntimeError):
    """Raised when the persisted image index cannot be trusted."""


class SafeImageLibrary(ImageLibrary):
    """ImageLibrary with fail-closed persistence and conservative visual dedupe.

    The original library API is intentionally preserved. Persistence is hardened:
    existing JSON is validated before writes, a rolling logical backup is made,
    the replacement is validated, then atomically installed. Perceptual duplicate
    checks also require compatible image geometry so a dHash collision cannot by
    itself merge unrelated assets.

    Legacy asset IDs remain compatible with ImageLibrary's 24-hex digest key. New
    safe imports additionally preserve the complete SHA-256 in metadata so exact
    identity/provenance can be audited without a destructive ID migration.
    """

    @property
    def backup_path(self) -> Path:
        return self.index_path.with_suffix(self.index_path.suffix + ".bak")

    def import_image(self, source: str | Path, *args, metadata: dict | None = None, **kwargs) -> ImageAsset:
        full_sha256 = self._full_sha256(Path(source))
        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("sha256_full", full_sha256)
        merged_metadata.setdefault("sha256", full_sha256)
        return super().import_image(source, *args, metadata=merged_metadata, **kwargs)

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
            # Validate before backing up. Never bless an already-corrupt index as
            # a usable backup and never overwrite it with an empty replacement.
            self._load()
            shutil.copy2(self.index_path, self.backup_path)

        tmp = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            check = json.loads(tmp.read_text(encoding="utf-8"))
            if not isinstance(check, dict):
                raise ImageLibraryCorruptionError("Temporary image index is not a JSON object")
            tmp.replace(self.index_path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def _full_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _source_visual_signature(source: str | Path) -> tuple[str, tuple[int, int]] | None:
        path = Path(source)
        try:
            with Image.open(path) as image:
                return ImageLibrary._dhash(image), image.size
        except (OSError, ValueError):
            return None

    @staticmethod
    def _is_visual_duplicate(
        fingerprint: str,
        source_size: tuple[int, int],
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
                max_hamming_distance=max_distance,
            )
        )

    def find_near_duplicate(
        self,
        source: str | Path,
        product_key: str = "",
        max_distance: int = ImageLibrary.VISUAL_DUPLICATE_DISTANCE,
    ) -> ImageAsset | None:
        signature = self._source_visual_signature(source)
        if signature is None:
            return None
        fingerprint, source_size = signature
        normalized_key = self.normalize_product_key(product_key)
        for data in self._load().values():
            asset = self._asset(data)
            if normalized_key and asset.product_key and self.normalize_product_key(asset.product_key) != normalized_key:
                continue
            if self._is_visual_duplicate(fingerprint, source_size, asset, max_distance):
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
        fingerprint, source_size = signature
        normalized_key = self.normalize_product_key(product_key)
        if not normalized_key:
            return None
        for data in self._load().values():
            asset = self._asset(data)
            asset_key = self.normalize_product_key(asset.product_key or asset.product_name)
            if not asset_key or asset_key == normalized_key:
                continue
            if self._is_visual_duplicate(fingerprint, source_size, asset, max_distance):
                return asset
        return None
