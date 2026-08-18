from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from srstudio.images.association import normalize_product_name
from srstudio.images.standalone_training import StandaloneImageSource


STANDALONE_STATE_VERSION = "g2-standalone-state-v1"
STANDALONE_TRAINER_VERSION = "g2-standalone-training-v2"


class StandaloneStateCorruptionError(RuntimeError):
    """Raised when standalone incremental state cannot be trusted."""


class StandaloneStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @property
    def backup_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".bak")

    def load(self) -> dict:
        if not self.path.exists():
            return {"version": STANDALONE_STATE_VERSION, "records": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise StandaloneStateCorruptionError(
                f"Standalone ingestion state is invalid and was not reset: {self.path}: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("records", {}), dict):
            raise StandaloneStateCorruptionError(
                f"Standalone ingestion state must be an object with records: {self.path}"
            )
        payload.setdefault("version", STANDALONE_STATE_VERSION)
        payload.setdefault("records", {})
        return payload

    def save(self, payload: dict) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("records", {}), dict):
            raise TypeError("Standalone state payload must be an object with records")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.load()
            shutil.copy2(self.path, self.backup_path)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            check = json.loads(temporary.read_text(encoding="utf-8"))
            if not isinstance(check, dict) or not isinstance(check.get("records", {}), dict):
                raise StandaloneStateCorruptionError("Temporary standalone state is invalid")
            temporary.replace(self.path)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def catalog_fingerprint(names) -> str:
    normalized = sorted(
        {
            normalize_product_name(str(name))
            for name in names
            if normalize_product_name(str(name))
        }
    )
    encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def standalone_source_fingerprint(source: StandaloneImageSource, catalog_digest: str) -> str:
    path = Path(source.path)
    payload = {
        "trainer_version": STANDALONE_TRAINER_VERSION,
        "source_path": str(path.resolve()),
        "file_sha256": file_sha256(path),
        "label": " ".join(str(source.label or "").split()),
        "product_name": " ".join(str(source.product_name or "").split()),
        "verified": bool(source.verified),
        "provenance": dict(source.provenance or {}),
        "catalog_sha256": str(catalog_digest or ""),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
