from __future__ import annotations

import json
import shutil
from pathlib import Path

from srstudio.images.library import ImageLibrary


class ImageLibraryCorruptionError(RuntimeError):
    """Raised when the persisted image index cannot be trusted."""


class SafeImageLibrary(ImageLibrary):
    """ImageLibrary persistence that never converts corruption into an empty bank.

    The original library API is intentionally preserved. Only persistence is
    hardened: existing JSON is validated before writes, a rolling logical backup
    is made, the replacement is validated, then atomically installed.
    """

    @property
    def backup_path(self) -> Path:
        return self.index_path.with_suffix(self.index_path.suffix + ".bak")

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
