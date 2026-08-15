from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Iterable, Mapping

from srstudio.core.models import Product
from srstudio.posters.core import PosterKind
from srstudio.posters.legacy_bridge import LegacyPosterBridge, legacy_engines_root, legacy_models_root


BatchProgress = Callable[[str, int, str], None]


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

    def render_many_to(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        outputs: Mapping[str, Path],
        campaign: str = "",
        *,
        width: int = 1772,
        height: int = 2480,
        on_progress: BatchProgress | None = None,
    ) -> dict[str, Path]:
        """Render many posters in one hidden PowerPoint session.

        The historical fitting functions are reused by the Turbo PowerShell engines;
        only the Office lifecycle changes. Models stay open and each source slide is
        duplicated in memory, filled, exported and discarded.
        """
        selected = [product for product in products if product.id in outputs]
        if not selected:
            return {}
        if not self.available():
            raise RuntimeError("Renderização Turbo requer Windows, PowerPoint e modelos SR instalados.")

        with tempfile.TemporaryDirectory(prefix="srstudio-poster-turbo-") as temp_name:
            job_path = Path(temp_name) / "jobs.json"
            jobs: list[dict[str, object]] = []
            for product in selected:
                job = (
                    self.bridge._wholesale_jobs([product])[0]
                    if kind == PosterKind.WHOLESALE
                    else self.bridge._promotion_jobs([product], campaign)[0]
                )
                job["output_png"] = str(Path(outputs[product.id]))
                jobs.append(job)
            job_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8-sig")

            engines = legacy_engines_root()
            models = legacy_models_root()
            if kind == PosterKind.WHOLESALE:
                script = engines / "TurboAtacadoPreview.ps1"
                arguments = [
                    "-JobsJson",
                    str(job_path),
                    "-BasePreviewEngine",
                    str(engines / "AtacadoPreview.ps1"),
                    "-Model",
                    str(models / "ATACADO.pptx"),
                    "-Width",
                    str(int(width)),
                    "-Height",
                    str(int(height)),
                ]
            else:
                script = engines / "TurboPromotionPreview.ps1"
                arguments = [
                    "-JobsJson",
                    str(job_path),
                    "-BasePreviewEngine",
                    str(engines / "PreviewEngine.ps1"),
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
                    "-Width",
                    str(int(width)),
                    "-Height",
                    str(int(height)),
                ]
            self._run_batch(script, arguments, on_progress=on_progress)

        rendered: dict[str, Path] = {}
        for product in selected:
            path = Path(outputs[product.id])
            if path.is_file() and path.stat().st_size > 1024:
                rendered[product.id] = path
        return rendered

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
            startupinfo, creationflags = cls._hidden_process_options()
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

    @classmethod
    def _run_batch(
        cls,
        script: Path,
        arguments: list[str],
        *,
        on_progress: BatchProgress | None = None,
    ) -> None:
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not shell or os.name != "nt":
            raise RuntimeError("PowerShell do Windows não disponível.")
        startupinfo, creationflags = cls._hidden_process_options()
        process = subprocess.Popen(
            [
                shell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                *arguments,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        output_lines: list[str] = []
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            output_lines.append(line)
            parts = line.split("|", 2)
            if len(parts) >= 2 and parts[0] in {"START", "OK", "ERR"}:
                try:
                    index = int(parts[1])
                except ValueError:
                    continue
                detail = parts[2] if len(parts) > 2 else ""
                if on_progress is not None:
                    on_progress(parts[0].lower(), index, detail)
        stderr = process.stderr.read() if process.stderr is not None else ""
        returncode = process.wait()
        if returncode != 0:
            detail = (stderr or "\n".join(output_lines) or "Falha no Turbo Renderer.").strip()
            raise RuntimeError(detail[-5000:])
        if not any(line.startswith("BATCH_DONE|") for line in output_lines):
            raise RuntimeError("PowerPoint encerrou sem confirmar a conclusão do lote Turbo.")

    @staticmethod
    def _hidden_process_options() -> tuple[object | None, int]:
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return startupinfo, creationflags

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
