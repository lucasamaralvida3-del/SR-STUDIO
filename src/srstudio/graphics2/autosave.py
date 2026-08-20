from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
import json
import os

from .model import GraphicsDocument
from .package import load_package, save_package


@dataclass(slots=True, frozen=True)
class RecoveryPoint:
    path: Path
    document_id: str
    document_name: str
    saved_at: datetime
    size: int


def default_autosave_root() -> Path:
    """Diretório estável e exclusivo do autosave/recovery do editor G2."""

    configured = str(os.environ.get("SR_STUDIO_G2_AUTOSAVE_ROOT") or "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".srstudio5" / "autosave-g2"


class AutosaveManager:
    """Autosave explícito, validado e recuperável; não cria threads ocultas.

    Mantém compatibilidade com o contrato integrado anterior (`latest_any` e
    configuração de embed no construtor), mas adota o hardening do CHAT 3:
    recovery portátil por padrão, verificação pós-gravação, validação de
    identidade ao recuperar e retenção baseada somente em gerações válidas.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        generations: int = 8,
        embed_local_assets: bool = True,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.generations = max(2, int(generations))
        self.embed_local_assets = bool(embed_local_assets)
        self._lock = RLock()

    def save(
        self,
        document: GraphicsDocument,
        *,
        embed_local_assets: bool | None = None,
    ) -> Path:
        with self._lock:
            folder = self.root / _safe_id(document.id)
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            path = folder / f"{stamp}.srscene"
            embed = self.embed_local_assets if embed_local_assets is None else bool(embed_local_assets)
            save_package(document, path, embed_local_assets=embed)

            # Nunca promova uma geração como recovery válido sem reabri-la.
            verified = load_package(path)
            if verified.id != document.id:
                path.unlink(missing_ok=True)
                raise ValueError("Autosave validado pertence a outro documento")

            _atomic_json(
                folder / "autosave.json",
                {
                    "document_id": document.id,
                    "document_name": document.name,
                    "latest": path.name,
                    "saved_at": stamp,
                    "embed_local_assets": embed,
                },
            )
            self._prune(folder)
            return path

    def latest(self, document_id: str) -> RecoveryPoint | None:
        points = self._points(self.root / _safe_id(document_id))
        return points[0] if points else None

    def latest_any(self) -> RecoveryPoint | None:
        points = self.list_recovery_points()
        return points[0] if points else None

    def recover(self, point: RecoveryPoint, *, extract_assets_to: str | Path | None = None) -> GraphicsDocument:
        with self._lock:
            document = load_package(point.path, extract_assets_to=extract_assets_to)
            if document.id != point.document_id:
                raise ValueError("Recovery point não pertence ao documento informado")
            return document

    def list_recovery_points(self, document_id: str | None = None) -> list[RecoveryPoint]:
        if document_id:
            return self._points(self.root / _safe_id(document_id))
        out: list[RecoveryPoint] = []
        if not self.root.exists():
            return out
        for folder in self.root.iterdir():
            if folder.is_dir():
                out.extend(self._points(folder))
        return sorted(out, key=lambda item: item.saved_at, reverse=True)

    def _points(self, folder: Path) -> list[RecoveryPoint]:
        if not folder.is_dir():
            return []
        points: list[RecoveryPoint] = []
        for path in folder.glob("*.srscene"):
            try:
                document = load_package(path)
                stat = path.stat()
                saved = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                points.append(RecoveryPoint(path, document.id, document.name, saved, stat.st_size))
            except (OSError, ValueError, KeyError):
                # Preserve o arquivo para diagnóstico, mas não conte uma geração
                # corrompida como recovery válido.
                continue
        return sorted(points, key=lambda item: item.saved_at, reverse=True)

    def _prune(self, folder: Path) -> None:
        valid = self._points(folder)
        for old in valid[self.generations :]:
            old.path.unlink(missing_ok=True)


def _safe_id(value: str) -> str:
    return "".join(ch for ch in str(value) if ch.isalnum() or ch in "-_")[:96] or "project"


def _atomic_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
