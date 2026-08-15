from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .library import ImageLibrary

DEFAULT_MANIFEST_URL = os.environ.get(
    "SR_STUDIO_IMAGE_BANK_URL",
    "https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/sr-studio-5-professional/image-bank/manifest.json",
)


@dataclass(slots=True)
class CloudBankStatus:
    state: str = "idle"
    local_version: int = 0
    remote_version: int = 0
    downloaded: int = 0
    reused: int = 0
    removed: int = 0
    total: int = 0
    bytes_downloaded: int = 0
    message: str = "Banco de imagens pronto"
    error: str = ""
    updated_at: str = ""
    details: list[str] = field(default_factory=list)


class ImageBankCloudSync:
    """Read-only official image bank sync with offline cache and SHA-256 validation."""

    def __init__(
        self,
        library: ImageLibrary,
        root: str | Path,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        timeout: float = 12.0,
    ) -> None:
        self.library = library
        self.root = Path(root)
        self.official_dir = self.root / "official"
        self.cache_dir = self.root / "cache"
        self.state_path = self.root / "cloud-state.json"
        self.manifest_cache = self.cache_dir / "manifest.json"
        self.manifest_url = manifest_url
        self.timeout = timeout
        self.official_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def sync(self, on_progress: Callable[[CloudBankStatus], None] | None = None) -> CloudBankStatus:
        local = self._state()
        status = CloudBankStatus(
            state="checking",
            local_version=int(local.get("version", 0) or 0),
            message="Banco de imagens · verificando atualizações...",
        )
        self._emit(status, on_progress)
        try:
            manifest = self._resolve_manifest(self.manifest_url)
            self._validate_manifest(manifest)
        except Exception as exc:
            status.state = "offline"
            status.error = str(exc)
            status.message = "Banco de imagens offline · usando cache local"
            status.updated_at = str(local.get("updated_at", ""))
            self._emit(status, on_progress)
            return status

        remote_version = int(manifest.get("bank_version", 0) or 0)
        assets = [item for item in manifest.get("assets", []) if item.get("status", "approved") == "approved"]
        status.remote_version = remote_version
        status.total = len(assets)
        remote_ids = {str(item["id"]) for item in assets}
        if remote_version <= status.local_version and self._official_files_valid(assets):
            self._deactivate_missing(remote_ids)
            status.state = "current"
            status.reused = len(assets)
            status.message = f"Banco de imagens atualizado · {len(assets)} imagens oficiais"
            self._write_manifest_cache(manifest)
            self._emit(status, on_progress)
            return status

        status.state = "syncing"
        for index, item in enumerate(assets, start=1):
            asset_id = str(item["id"])
            suffix = Path(str(item.get("filename") or item.get("url") or ".webp")).suffix.lower() or ".webp"
            destination = self.official_dir / f"{asset_id}{suffix}"
            expected = str(item["sha256"]).lower()
            if destination.is_file() and self._sha256(destination) == expected:
                status.reused += 1
            else:
                status.message = f"Banco de imagens · baixando {index}/{len(assets)}"
                self._emit(status, on_progress)
                size = self._download(str(item["url"]), destination, expected)
                status.downloaded += 1
                status.bytes_downloaded += size
            self._register_official(destination, item)

        for file in self.official_dir.iterdir():
            if file.is_file() and file.stem not in remote_ids:
                file.unlink(missing_ok=True)
                status.removed += 1
        self._deactivate_missing(remote_ids)

        now = datetime.now(timezone.utc).isoformat()
        self._write_manifest_cache(manifest)
        self._save_state({"version": remote_version, "updated_at": now, "asset_count": len(assets)})
        status.state = "updated"
        status.local_version = remote_version
        status.updated_at = now
        status.message = f"Banco SR atualizado · {len(assets)} imagens · {status.downloaded} nova(s)"
        self._emit(status, on_progress)
        return status

    def check(self) -> CloudBankStatus:
        return self.sync()

    def local_version(self) -> int:
        return int(self._state().get("version", 0) or 0)

    def _resolve_manifest(self, url: str) -> dict:
        first = self._fetch_json(url)
        redirect = str(first.get("redirect_manifest_url") or "").strip()
        if not redirect:
            return first
        if not redirect.startswith("https://"):
            raise ValueError("Redirecionamento do Banco SR deve usar HTTPS")
        redirected = self._fetch_json(redirect)
        redirected["_bootstrap_url"] = url
        redirected["_resolved_manifest_url"] = redirect
        return redirected

    def _register_official(self, path: Path, item: dict) -> None:
        asset = self.library.import_image(
            path,
            product_key=str(item.get("product_key") or item.get("product_name") or ""),
            product_name=str(item.get("product_name") or item.get("product_key") or ""),
            aliases=tuple(item.get("aliases") or ()),
            tags=tuple(item.get("tags") or ("oficial", "cloud")),
            kind="product",
            confidence=1.0,
            review_status="accepted",
            source_kind="cloud",
            source_file="SR Image Cloud",
            preferred=bool(item.get("preferred", False)),
            metadata={
                "official": True,
                "official_active": True,
                "cloud_asset_id": str(item.get("id") or ""),
                "cloud_version": int(item.get("version", 1) or 1),
                "ean": str(item.get("ean") or ""),
                "category": str(item.get("category") or ""),
                "remote_sha256": str(item.get("sha256") or ""),
            },
        )
        if item.get("preferred") and not asset.preferred:
            self.library.set_preferred(asset.id, True)

    def _deactivate_missing(self, remote_ids: set[str]) -> None:
        for asset in self.library.all():
            if asset.source != "cloud":
                continue
            cloud_id = str(asset.metadata.get("cloud_asset_id") or "")
            if cloud_id and cloud_id not in remote_ids and asset.review_status != "rejected":
                self.library.update_metadata(
                    asset.id,
                    review_status="rejected",
                    preferred=False,
                    metadata={**asset.metadata, "official_active": False},
                )

    def _download(self, url: str, destination: Path, expected_sha: str) -> int:
        request = urllib.request.Request(url, headers={"User-Agent": "SR-Studio/5 ImageBankSync"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            with tempfile.NamedTemporaryFile(delete=False, dir=self.cache_dir, suffix=".download") as temp:
                shutil.copyfileobj(response, temp)
                temp_path = Path(temp.name)
        try:
            actual = self._sha256(temp_path)
            if actual != expected_sha:
                raise ValueError(f"SHA-256 inválido para {destination.name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_path.replace(destination)
            return destination.stat().st_size
        finally:
            temp_path.unlink(missing_ok=True)

    def _official_files_valid(self, assets: list[dict]) -> bool:
        for item in assets:
            suffix = Path(str(item.get("filename") or item.get("url") or ".webp")).suffix.lower() or ".webp"
            path = self.official_dir / f"{item['id']}{suffix}"
            if not path.is_file() or self._sha256(path) != str(item["sha256"]).lower():
                return False
        return True

    def _fetch_json(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": "SR-Studio/5 ImageBankSync"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8-sig"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Não foi possível consultar o Banco SR: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Manifesto do Banco SR inválido")
        return payload

    @staticmethod
    def _validate_manifest(payload: dict) -> None:
        if payload.get("format") != "SR_IMAGE_BANK_1":
            raise ValueError("Formato do manifesto do Banco SR não reconhecido")
        if not isinstance(payload.get("assets", []), list):
            raise ValueError("Lista de imagens do Banco SR inválida")
        for item in payload.get("assets", []):
            if item.get("status", "approved") != "approved":
                continue
            for key in ("id", "url", "sha256"):
                if not item.get(key):
                    raise ValueError(f"Imagem oficial sem campo obrigatório: {key}")

    def _state(self) -> dict:
        if not self.state_path.is_file():
            return {}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self, payload: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.state_path)

    def _write_manifest_cache(self, payload: dict) -> None:
        self.manifest_cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()

    @staticmethod
    def _emit(status: CloudBankStatus, callback: Callable[[CloudBankStatus], None] | None) -> None:
        if callback is not None:
            callback(status)
