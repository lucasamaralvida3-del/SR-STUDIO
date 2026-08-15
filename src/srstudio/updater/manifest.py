from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    channel: str
    package: str
    sha256: str
    size: int
    minimum_launcher: str = "5.0.0"
    notes: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "UpdateManifest":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def verify_package(self, path: str | Path) -> bool:
        package = Path(path)
        if not package.exists() or package.stat().st_size != self.size:
            return False
        digest = hashlib.sha256()
        with package.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower() == self.sha256.lower()


def build_manifest(package: str | Path, version: str, channel: str, notes: str = "") -> UpdateManifest:
    path = Path(package)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return UpdateManifest(version, channel, path.name, digest, path.stat().st_size, notes=notes)
