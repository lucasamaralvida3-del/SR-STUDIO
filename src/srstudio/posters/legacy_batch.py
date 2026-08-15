from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import pypdfium2 as pdfium
from PIL import Image

from srstudio.core.models import Product
from srstudio.posters.core import PosterKind
from srstudio.posters.legacy_bridge import LegacyPosterBridge, legacy_engines_root, legacy_models_root


LegacyBatchProgress = Callable[[str, int, str], None]


@dataclass(slots=True)
class LegacyBatchRenderResult:
    files: dict[int, Path] = field(default_factory=dict)
    errors: dict[int, str] = field(default_factory=dict)
    batch_error: str = ""


class LegacyBatchRenderer:
    """Run the proven historical PowerPoint engines unchanged.

    Speed comes from the engines' existing one-PowerPoint-session batch lifecycle.
    SR Studio only observes their stdout, hides the Office window when possible and
    rasterizes the resulting vector PDFs with PDFium for instant previews.
    """

    def __init__(self) -> None:
        self.bridge = LegacyPosterBridge()

    def render_pdfs(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        output_dir: str | Path,
        campaign: str = "",
        *,
        on_progress: LegacyBatchProgress | None = None,
    ) -> LegacyBatchRenderResult:
        selected = list(products)
        result = LegacyBatchRenderResult()
        if not selected:
            return result
        if not self.bridge.assets_available():
            result.batch_error = "Os engines/modelos históricos SR não estão disponíveis."
            return result
        if not self.bridge.windows_available():
            result.batch_error = "PowerPoint em lote está disponível apenas no Windows."
            return result

        target = Path(output_dir)
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="srstudio-legacy-batch-") as temp_name:
            jobs_path = Path(temp_name) / "jobs.json"
            jobs = (
                self.bridge._wholesale_jobs(selected)
                if kind == PosterKind.WHOLESALE
                else self.bridge._promotion_jobs(selected, campaign)
            )
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8-sig")
            script, args = self._engine_command(kind, jobs_path, target)
            result = self._run(script, args, target, on_progress=on_progress)
        return result

    @staticmethod
    def rasterize_pdf(
        pdf_path: str | Path,
        png_path: str | Path,
        *,
        width: int,
        height: int,
    ) -> Path:
        """Render first PDF page to the exact print-preview size without PowerPoint."""
        source = Path(pdf_path)
        destination = Path(png_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        document = pdfium.PdfDocument(str(source))
        try:
            if len(document) < 1:
                raise RuntimeError(f"PDF sem páginas: {source.name}")
            page = document[0]
            try:
                page_width, page_height = page.get_size()
                if page_width <= 0 or page_height <= 0:
                    raise RuntimeError(f"Página PDF inválida: {source.name}")
                scale = max(width / page_width, height / page_height)
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil().convert("RGB")
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()

        try:
            if image.size != (width, height):
                image = image.resize((width, height), Image.Resampling.LANCZOS)
            image.save(destination, "PNG", optimize=False)
        finally:
            image.close()
        return destination

    def _engine_command(self, kind: PosterKind, jobs: Path, output: Path) -> tuple[Path, list[str]]:
        engines = legacy_engines_root()
        models = legacy_models_root()
        if kind == PosterKind.WHOLESALE:
            return (
                engines / "AtacadoEngine.ps1",
                ["-JobsJson", str(jobs), "-OutputDir", str(output), "-Model", str(models / "ATACADO.pptx")],
            )
        return (
            engines / "PowerPointEngine.ps1",
            [
                "-JobsJson",
                str(jobs),
                "-OutputDir",
                str(output),
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
            ],
        )

    def _run(
        self,
        script: Path,
        args: list[str],
        output_dir: Path,
        *,
        on_progress: LegacyBatchProgress | None,
    ) -> LegacyBatchRenderResult:
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not shell:
            return LegacyBatchRenderResult(batch_error="Windows PowerShell não encontrado.")

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        process = subprocess.Popen(
            [
                shell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                *args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        result = LegacyBatchRenderResult()
        lines: list[str] = []
        confirmed_done = False
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.strip()
            if not line:
                continue
            lines.append(line)
            if line.startswith("PPTPID|"):
                try:
                    self._hide_process_windows(int(line.split("|", 1)[1]))
                except (ValueError, OSError):
                    pass
                continue
            if line.startswith("BATCH_DONE|"):
                confirmed_done = True
                continue

            parts = line.split("|", 3)
            if len(parts) >= 3 and parts[0] == "STAGE":
                try:
                    index = int(parts[1])
                except ValueError:
                    continue
                if on_progress is not None:
                    on_progress("stage", index, parts[2])
                continue
            if len(parts) >= 3 and parts[0] == "OK":
                try:
                    index = int(parts[1])
                except ValueError:
                    continue
                pdf = Path(parts[2])
                if pdf.is_file():
                    result.files[index] = pdf
                if on_progress is not None:
                    on_progress("ok", index, str(pdf))
                continue
            if len(parts) >= 3 and parts[0] == "ERR":
                try:
                    index = int(parts[1])
                except ValueError:
                    continue
                detail = parts[2] if len(parts) == 3 else "|".join(parts[2:])
                result.errors[index] = detail
                if on_progress is not None:
                    on_progress("err", index, detail)

        stderr = process.stderr.read() if process.stderr is not None else ""
        returncode = process.wait()

        # Recover already-written PDFs even if the promotion engine stopped on a later item.
        for candidate in output_dir.glob("*.pdf"):
            match = re.match(r"^(\d{3})_", candidate.name)
            if match:
                result.files.setdefault(int(match.group(1)), candidate)

        error_file = output_dir / "errors.json"
        if error_file.is_file():
            try:
                payload = json.loads(error_file.read_text(encoding="utf-8-sig"))
                for item in payload if isinstance(payload, list) else [payload]:
                    if not isinstance(item, dict):
                        continue
                    try:
                        index = int(item.get("index", 0))
                    except (TypeError, ValueError):
                        continue
                    if index > 0:
                        result.errors[index] = str(item.get("message", "Falha no cartaz."))
            except (OSError, ValueError, TypeError):
                pass

        if returncode != 0:
            result.batch_error = (stderr or "\n".join(lines) or "Falha no engine histórico.").strip()[-5000:]
        elif not confirmed_done:
            result.batch_error = "O engine histórico encerrou sem confirmar BATCH_DONE."
        return result

    @staticmethod
    def _hide_process_windows(process_id: int) -> None:
        """Best-effort hide; failure never affects poster generation."""
        if os.name != "nt" or process_id <= 0:
            return
        user32 = ctypes.windll.user32
        enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        @enum_proc
        def callback(hwnd, _lparam):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == process_id and user32.IsWindowVisible(hwnd):
                user32.ShowWindow(hwnd, 0)
            return True

        user32.EnumWindows(callback, 0)
