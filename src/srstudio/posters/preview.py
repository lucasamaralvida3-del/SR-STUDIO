from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from srstudio.core.models import Product
from srstudio.posters.core import PosterKind
from srstudio.posters.legacy_bridge import LegacyPosterBridge, legacy_engines_root, legacy_models_root


class LegacyPosterPreviewService:
    """Generate faithful previews with the same historical PowerPoint models used for print."""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self.cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path.home() / ".srstudio5" / "cache" / "poster-previews"
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bridge = LegacyPosterBridge()

    @staticmethod
    def available() -> bool:
        return LegacyPosterBridge.assets_available() and LegacyPosterBridge.windows_available()

    def render(
        self,
        product: Product,
        kind: PosterKind,
        campaign: str = "",
        *,
        width: int = 900,
        height: int | None = None,
        cache_namespace: str = "preview-v3",
    ) -> Path:
        if not self.available():
            raise RuntimeError("Prévia oficial requer Windows, Microsoft PowerPoint e os modelos SR instalados.")
        if height is None:
            height = 1260 if kind == PosterKind.WHOLESALE else 1250
        destination = self.cache_dir / f"{self._cache_key(product, kind, campaign, width, height, cache_namespace)}.png"
        if destination.is_file() and destination.stat().st_size > 1024:
            return destination

        with tempfile.TemporaryDirectory(prefix="srstudio-poster-preview-") as temp_name:
            job_path = Path(temp_name) / "job.json"
            if kind == PosterKind.WHOLESALE:
                job = self.bridge._wholesale_jobs([product])[0]
                script = legacy_engines_root() / "AtacadoPreview.ps1"
                arguments = [
                    "-JobJson",
                    str(job_path),
                    "-OutputPng",
                    str(destination),
                    "-Model",
                    str(legacy_models_root() / "ATACADO.pptx"),
                ]
            else:
                job = self.bridge._promotion_jobs([product], campaign)[0]
                models = legacy_models_root()
                script = legacy_engines_root() / "PreviewEngine.ps1"
                arguments = [
                    "-JobJson",
                    str(job_path),
                    "-OutputPng",
                    str(destination),
                    "-Model1",
                    str(models / "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx"),
                    "-Model2",
                    str(models / "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx"),
                    "-Model1Limit",
                    str(models / "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx"),
                    "-Model2Limit",
                    str(models / "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"),
                    "-ClubModel",
                    str(models / "CLUBE_EXCLUSIVO.pptx"),
                    "-ClubModelLimit",
                    str(models / "CLUBE_EXCLUSIVO_COM_LIMITE.pptx"),
                    "-SaleModel",
                    str(models / "CARTAZ_VENDA.pptx"),
                ]
            job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8-sig")
            destination.unlink(missing_ok=True)
            self._run(script, arguments, width=width, height=height)

        if not destination.is_file() or destination.stat().st_size <= 1024:
            raise RuntimeError("O PowerPoint encerrou sem gerar a prévia oficial.")
        return destination

    @classmethod
    def _run(cls, script: Path, arguments: list[str], *, width: int, height: int) -> None:
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not shell or os.name != "nt":
            raise RuntimeError("PowerShell do Windows não disponível.")

        with tempfile.TemporaryDirectory(prefix="srstudio-silent-preview-") as temp_name:
            silent_script = Path(temp_name) / script.name
            source = script.read_text(encoding="utf-8-sig")
            silent_script.write_text(
                cls._silent_script_source(source, width=width, height=height),
                encoding="utf-8-sig",
            )

            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            completed = subprocess.run(
                [
                    shell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(silent_script),
                    *arguments,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "Falha ao gerar prévia oficial.").strip()
            raise RuntimeError(detail[-4000:])

    @staticmethod
    def _silent_script_source(source: str, *, width: int = 900, height: int = 1250) -> str:
        replacement = "try { $ppt.Visible = 0 } catch { }"
        result = re.sub(r"\$ppt\.Visible\s*=\s*-1", replacement, source, flags=re.IGNORECASE)
        result = re.sub(
            r"\.Export\(\$OutputPng\s*,\s*[\"']PNG[\"']\s*,\s*\d+\s*,\s*\d+\s*\)",
            f'.Export($OutputPng, "PNG", {int(width)}, {int(height)})',
            result,
            flags=re.IGNORECASE,
        )
        return result

    @staticmethod
    def _cache_key(
        product: Product,
        kind: PosterKind,
        campaign: str,
        width: int,
        height: int,
        namespace: str,
    ) -> str:
        payload = {
            "kind": kind.value,
            "campaign": campaign,
            "product": product.to_dict(),
            "poster_type": product.metadata.get("promotion_type"),
            "engine": "legacy-preview-v3-silent-resizable",
            "width": width,
            "height": height,
            "namespace": namespace,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:40]
