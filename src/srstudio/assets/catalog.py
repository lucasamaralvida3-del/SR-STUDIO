from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AssetRecord:
    id: str
    kind: str
    name: str
    path: str
    checksum: str
    tags: tuple[str, ...] = ()


class AssetCatalog:
    """Biblioteca local para logos, fundos, selos, imagens e elementos reutilizáveis."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "assets.json"
        self.records: dict[str, AssetRecord] = {}
        self._load()

    def import_asset(self, source: str | Path, kind: str, tags: tuple[str, ...] = ()) -> AssetRecord:
        src = Path(source)
        data = src.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        asset_id = checksum[:16]
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{asset_id}{src.suffix.lower()}"
        if not target.exists():
            shutil.copy2(src, target)
        record = AssetRecord(asset_id, kind, src.stem, str(target), checksum, tags)
        self.records[asset_id] = record
        self._save()
        return record

    def find(self, *, kind: str | None = None, text: str = "") -> list[AssetRecord]:
        query = text.strip().lower()
        result = []
        for record in self.records.values():
            if kind and record.kind != kind:
                continue
            haystack = " ".join((record.name, *record.tags)).lower()
            if query and query not in haystack:
                continue
            result.append(record)
        return sorted(result, key=lambda item: item.name.lower())

    def remove(self, asset_id: str, delete_file: bool = False) -> bool:
        record = self.records.pop(asset_id, None)
        if record is None:
            return False
        if delete_file:
            Path(record.path).unlink(missing_ok=True)
        self._save()
        return True

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        for item in raw:
            item["tags"] = tuple(item.get("tags", ()))
            record = AssetRecord(**item)
            self.records[record.id] = record

    def _save(self) -> None:
        payload = [asdict(item) for item in self.records.values()]
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
