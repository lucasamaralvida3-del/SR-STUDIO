from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from srstudio.updater.manifest import UpdateManifest


@dataclass(frozen=True, slots=True)
class UpdateResult:
    ok: bool
    message: str
    active_path: str = ""
    backup_path: str = ""


class UpdateTransaction:
    """Atualização local transacional: validar -> staging -> backup -> ativar."""

    def __init__(self, install_root: str | Path) -> None:
        self.root = Path(install_root)
        self.active = self.root / "app"
        self.backup = self.root / "app.previous"
        self.staging = self.root / "app.staging"
        self.root.mkdir(parents=True, exist_ok=True)

    def stage_directory(self, source: str | Path) -> Path:
        src = Path(source)
        if not src.is_dir():
            raise ValueError("A origem da atualização precisa ser uma pasta")
        if self.staging.exists():
            shutil.rmtree(self.staging)
        shutil.copytree(src, self.staging)
        return self.staging

    def validate_package(self, manifest: UpdateManifest, package: str | Path) -> bool:
        return manifest.verify_package(package)

    def activate_staging(self) -> UpdateResult:
        if not self.staging.exists():
            return UpdateResult(False, "Nenhuma atualização em staging.")
        try:
            if self.backup.exists():
                shutil.rmtree(self.backup)
            if self.active.exists():
                self.active.replace(self.backup)
            self.staging.replace(self.active)
            return UpdateResult(True, "Atualização ativada.", str(self.active), str(self.backup))
        except Exception as exc:
            self.rollback()
            return UpdateResult(False, f"Falha ao ativar atualização: {exc}", str(self.active), str(self.backup))

    def rollback(self) -> UpdateResult:
        try:
            if self.active.exists() and self.backup.exists():
                shutil.rmtree(self.active)
            if self.backup.exists():
                self.backup.replace(self.active)
                return UpdateResult(True, "Rollback concluído.", str(self.active))
            return UpdateResult(False, "Não existe versão anterior para restaurar.")
        except Exception as exc:
            return UpdateResult(False, f"Falha no rollback: {exc}")

    def cleanup(self) -> None:
        if self.staging.exists():
            shutil.rmtree(self.staging)
