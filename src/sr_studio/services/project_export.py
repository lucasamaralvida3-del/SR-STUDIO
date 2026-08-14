from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from Encartes3Engine import local_editor_url
from services.export_profiles import export_images
from services.project_store import load_project


def _edge_executable() -> Path | None:
    candidates = [
        Path(os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")),
        Path(os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")),
        Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")),
    ]
    for path in candidates:
        if path.is_file():
            return path
    found = shutil.which("msedge") or shutil.which("microsoft-edge")
    return Path(found) if found else None


def _pages(project: dict[str, Any]) -> list[dict[str, Any]]:
    state = project.get("state") or {}
    enc = state.get("encartes_state") or {}
    return list(enc.get("pages") or state.get("pages") or [])


def capture_project_pages(project_id: str, output_dir: str | Path) -> list[Path]:
    edge = _edge_executable()
    if not edge:
        raise RuntimeError("Microsoft Edge não foi encontrado. Ele é necessário para renderizar as páginas do Encartes.")
    project = load_project(project_id, prefer_autosave=False)
    pages = _pages(project)
    if not pages:
        raise ValueError("O projeto não possui páginas para exportar.")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = local_editor_url()
    results: list[Path] = []
    for index, page in enumerate(pages):
        width = max(320, min(5000, round(float(page.get("width") or 794))))
        height = max(320, min(5000, round(float(page.get("height") or 1123))))
        target = output_dir / f"pagina_{index + 1:03d}.png"
        url = f"{base}?v5project={quote(project_id, safe='')}&v5capture=1&exportPage={index}"
        cmd = [
            str(edge),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--disable-extensions",
            "--no-first-run",
            "--no-default-browser-check",
            "--force-device-scale-factor=1",
            f"--window-size={width},{height}",
            "--virtual-time-budget=5000",
            f"--screenshot={target}",
            url,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if proc.returncode != 0 or not target.is_file() or target.stat().st_size < 1000:
            detail = (proc.stderr or proc.stdout or "Falha desconhecida").strip()[-1600:]
            raise RuntimeError(f"Falha ao renderizar a página {index + 1}: {detail}")
        results.append(target)
    return results


def export_project(project_id: str, profile: dict[str, Any], output_dir: str | Path, prefix: str = "srstudio") -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="srstudio5-render-") as td:
        rendered = capture_project_pages(project_id, Path(td))
        files = export_images(rendered, profile, output_dir, prefix=prefix)
    return {
        "project_id": project_id,
        "profile": profile.get("name") or profile.get("id") or "",
        "pages": len(rendered),
        "files": [str(x) for x in files],
    }
