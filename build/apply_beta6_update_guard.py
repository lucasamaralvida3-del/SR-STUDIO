from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_FILE = ROOT / "src" / "sr_studio" / "SR_Studio_Gerador.py"
LAUNCHER_FILE = ROOT / "launcher" / "files" / "SRStudioLauncher.ps1"

APP_MARKER = "SR5_BETA6_DIRECT_LAUNCH_GUARD"
LAUNCHER_MARKER = "SR5_BETA6_LAUNCH_GUARD"


def patch_app() -> None:
    text = APP_FILE.read_text(encoding="utf-8-sig")
    if APP_MARKER in text:
        return
    anchor = "from datetime import datetime\n\n"
    if anchor not in text:
        raise RuntimeError("Ancora de imports do aplicativo nao encontrada")
    block = r'''from datetime import datetime

# SR5_BETA6_DIRECT_LAUNCH_GUARD
# Quando a copia instalada e aberta diretamente (por atalho antigo, Python ou pin da barra),
# ela redireciona a abertura para o Bootstrap para que a verificacao de atualizacoes nunca seja pulada.
def _sr5_require_official_launcher():
    if os.name != "nt":
        return
    if str(os.environ.get("SR_STUDIO_LAUNCHED_BY_UPDATER", "")).strip() == "1":
        return
    local_app = str(os.environ.get("LOCALAPPDATA", "")).strip()
    if not local_app:
        return
    sr_root = Path(local_app) / "SRStudio"
    installed_app = sr_root / "App"
    try:
        here = Path(__file__).resolve()
        app_root = installed_app.resolve()
        here.relative_to(app_root)
    except Exception:
        # Desenvolvimento/CI ou copia fora da instalacao oficial: nao interceptar.
        return
    bootstrap = sr_root / "Launcher" / "SRStudioBootstrap.ps1"
    if not bootstrap.exists():
        return
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.exists():
        return
    env = os.environ.copy()
    env["SR_STUDIO_REDIRECTED_TO_LAUNCHER"] = "1"
    try:
        subprocess.Popen(
            [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(bootstrap)],
            cwd=str(sr_root),
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return
    raise SystemExit(0)

_sr5_require_official_launcher()

'''
    text = text.replace(anchor, block, 1)
    APP_FILE.write_text(text, encoding="utf-8")


def patch_launcher() -> None:
    text = LAUNCHER_FILE.read_text(encoding="utf-8-sig")
    text = text.replace("$LauncherVersion = '4.0.1-hybrid.base3.1'", "$LauncherVersion = '4.0.1-hybrid.base3.2'", 1)
    if LAUNCHER_MARKER not in text:
        anchor = "function Start-SrDesktop {\n"
        if anchor not in text:
            raise RuntimeError("Funcao Start-SrDesktop nao encontrada")
        helper = r'''# SR5_BETA6_LAUNCH_GUARD
# Todo Core iniciado pelo Launcher recebe um marcador de processo. A copia instalada usa esse
# marcador para distinguir uma abertura oficial de uma abertura direta por atalho antigo.
function Start-SrGuardedProcess([string]$FilePath,$ArgumentList,[string]$WorkingDirectory) {
  $previousGuard = [Environment]::GetEnvironmentVariable('SR_STUDIO_LAUNCHED_BY_UPDATER','Process')
  $previousLauncherVersion = [Environment]::GetEnvironmentVariable('SR_STUDIO_LAUNCHER_VERSION','Process')
  $env:SR_STUDIO_LAUNCHED_BY_UPDATER = '1'
  $env:SR_STUDIO_LAUNCHER_VERSION = $LauncherVersion
  try {
    if($null -ne $ArgumentList -and @($ArgumentList).Count -gt 0) {
      Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory
    } else {
      Start-Process -FilePath $FilePath -WorkingDirectory $WorkingDirectory
    }
  }
  finally {
    if($null -eq $previousGuard) { Remove-Item Env:SR_STUDIO_LAUNCHED_BY_UPDATER -ErrorAction SilentlyContinue } else { $env:SR_STUDIO_LAUNCHED_BY_UPDATER = $previousGuard }
    if($null -eq $previousLauncherVersion) { Remove-Item Env:SR_STUDIO_LAUNCHER_VERSION -ErrorAction SilentlyContinue } else { $env:SR_STUDIO_LAUNCHER_VERSION = $previousLauncherVersion }
  }
}

function Start-SrDesktop {
'''
        text = text.replace(anchor, helper, 1)
        text = text.replace("Start-Process -FilePath $entry -WorkingDirectory $AppDir", "Start-SrGuardedProcess $entry @() $AppDir")
        text = text.replace("Start-Process -FilePath $pythonPath -ArgumentList @('\\\"' + $entry + '\\\"') -WorkingDirectory $AppDir", "Start-SrGuardedProcess $pythonPath @('\\\"' + $entry + '\\\"') $AppDir")
    LAUNCHER_FILE.write_text(text, encoding="utf-8")


def main() -> None:
    patch_app()
    patch_launcher()
    app = APP_FILE.read_text(encoding="utf-8-sig")
    launcher = LAUNCHER_FILE.read_text(encoding="utf-8-sig")
    assert APP_MARKER in app
    assert "SR_STUDIO_LAUNCHED_BY_UPDATER" in app
    assert LAUNCHER_MARKER in launcher
    assert "4.0.1-hybrid.base3.2" in launcher
    print("BETA6_UPDATE_GUARD_APPLIED")


if __name__ == "__main__":
    main()
