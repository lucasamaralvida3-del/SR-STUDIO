from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess

import pytest

import srstudio


REPO = Path(srstudio.__file__).resolve().parents[2]
LAUNCHER_DIR = REPO / "launcher" / "files"


def _text(name: str) -> str:
    return (LAUNCHER_DIR / name).read_text(encoding="utf-8-sig")


def test_bootstrap_invokes_graphics2_component_before_desktop_launcher():
    source = _text("SRStudioBootstrap.ps1")
    component_index = source.index("& $graphics2Updater -FullRepair:$FullRepair")
    launcher_index = source.index("& $launcherToRun -RepairOnly:$RepairOnly")

    assert "$BootstrapVersion = '4.0.1-hybrid.setup3'" in source
    assert "SRGraphics2Component.ps1" in source
    assert "graphics2_host" in source
    assert component_index < launcher_index


def test_component_contract_is_optional_atomic_and_does_not_enable_feature_flags():
    source = _text("SRGraphics2Component.ps1")

    assert "srstudio/graphics2-host-runtime-1" in source
    assert "srstudio/graphics2-host-install-1" in source
    assert "Get-G2Property $component 'required' $false" in source
    assert "Graphics2Host.staging-" in source
    assert "Graphics2Host.previous" in source
    assert "Assert-G2Runtime $sourceRoot $expectedVersion $true" in source
    assert "Assert-G2Runtime $staging $expectedVersion $true" in source
    assert "Assert-G2Runtime $InstallDir $expectedVersion $true" in source
    assert "SHA-256 do ZIP Graphics2Host inválido" in source
    assert "Feature flag permaneceu inalterada" in source
    assert "feature-flags.json" not in source
    assert ".set(\"graphics_engine_2\"" not in source
    # O updater é invocado com `&` dentro do Bootstrap. `exit` encerraria toda
    # a sessão PowerShell e impediria o Desktop Core de abrir após um no-op.
    assert "exit 0" not in source


def test_current_stable_manifest_does_not_activate_graphics2_host_yet():
    manifest = json.loads((REPO / "stable" / "manifest.json").read_text(encoding="utf-8-sig"))
    assert "graphics2_host" not in manifest


@pytest.mark.skipif(os.name != "nt", reason="Parser PowerShell disponível no gate Windows")
def test_graphics2_launcher_powershell_scripts_parse_on_windows():
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        pytest.skip("Windows PowerShell não encontrado")
    for name in ("SRStudioBootstrap.ps1", "SRGraphics2Component.ps1"):
        path = LAUNCHER_DIR / name
        escaped_path = str(path).replace("'", "''")
        command = (
            "$tokens=$null;$errors=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}',"
            "[ref]$tokens,[ref]$errors)|Out-Null;"
            "if($errors.Count -gt 0){$errors|ForEach-Object{Write-Error $_.Message};exit 1}"
        )
        completed = subprocess.run([powershell, "-NoProfile", "-Command", command], capture_output=True, text=True)
        assert completed.returncode == 0, completed.stderr or completed.stdout
