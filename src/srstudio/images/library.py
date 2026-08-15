from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image


SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


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

    @property
    def megapixels(self) -> float:
        return round((self.width * self.height) / 1_000_000, 2)


class ImageLibrary:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.assets_dir = self.root / "assets"
        self.index_path = self.root / "index.json"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def import_image(self, source: str | Path, product_key: str = "", tags: tuple[str, ...] = ()) -> ImageAsset:
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
        asset = ImageAsset(
            id=digest,
            path=str(target),
            original_name=source.name,
            width=width,
            height=height,
            mode=mode,
            bytes_size=target.stat().st_size,
            imported_at=datetime.now().isoformat(timespec="seconds"),
            product_key=product_key,
            tags=tuple(tags),
        )
        index = self._load()
        index[digest] = asdict(asset)
        self._save(index)
        return asset

    def find_for_product(self, product_key: str) -> list[ImageAsset]:
        if not product_key:
            return []
        return [self._asset(data) for data in self._load().values() if data.get("product_key") == product_key]

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
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, payload: dict) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    @staticmethod
    def _hash(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()[:24]

    @staticmethod
    def _asset(data: dict) -> ImageAsset:
        data = dict(data)
        data["tags"] = tuple(data.get("tags") or ())
        return ImageAsset(**data)
