from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher" / "files" / "SRStudioLauncher.ps1"
MANIFEST = ROOT / "manifests" / "launcher.json"
DIST = ROOT / "dist"

NEW_FUNC = r'''function Ensure-SrPythonRuntime {
  $pythonRoot = Join-Path $RuntimeDir 'python'
  New-Item -ItemType Directory -Path $pythonRoot -Force | Out-Null

  $candidateList = New-Object 'System.Collections.Generic.List[string]'
  function Add-SrPythonCandidate([string]$Candidate) {
    if(-not $Candidate) { return }
    try { $expanded = Expand-SrEnv $Candidate } catch { $expanded = $Candidate }
    if(-not $expanded) { return }
    if($expanded -match '\\WindowsApps\\') { return }
    if((Test-Path -LiteralPath $expanded -PathType Leaf) -and -not $candidateList.Contains($expanded)) {
      $candidateList.Add($expanded)
    }
  }

  # Primeiro, reutiliza Python 3.12 real ja existente. Nao força instalacao privada.
  Add-SrPythonCandidate (Join-Path $pythonRoot 'pythonw.exe')
  Add-SrPythonCandidate (Join-Path $pythonRoot 'python.exe')
  Add-SrPythonCandidate ([string](Get-SrProperty $cfg 'python_command' ''))
  Add-SrPythonCandidate (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe')
  Add-SrPythonCandidate (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
  if($env:ProgramFiles) {
    Add-SrPythonCandidate (Join-Path $env:ProgramFiles 'Python312\pythonw.exe')
    Add-SrPythonCandidate (Join-Path $env:ProgramFiles 'Python312\python.exe')
  }
  try {
    $pyCmd = Get-Command py.exe -ErrorAction SilentlyContinue
    if($pyCmd -and $pyCmd.Source -notmatch '\\WindowsApps\\') {
      $resolved = (& $pyCmd.Source -3.12 -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
      if($resolved) { Add-SrPythonCandidate (([string]$resolved).Trim()) }
    }
  } catch { }
  foreach($cmdName in @('pythonw.exe','python.exe')) {
    try {
      $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
      if($cmd) { Add-SrPythonCandidate $cmd.Source }
    } catch { }
  }

  function Resolve-SrPythonPair($Candidates) {
    foreach($candidate in @($Candidates)) {
      $leaf = [IO.Path]::GetFileName($candidate).ToLowerInvariant()
      $dir = Split-Path $candidate -Parent
      if($leaf -eq 'pythonw.exe') {
        $wexe = $candidate
        $exe = Join-Path $dir 'python.exe'
      } else {
        $exe = $candidate
        $wexe = Join-Path $dir 'pythonw.exe'
      }
      if(-not (Test-Path -LiteralPath $exe -PathType Leaf)) { continue }
      try {
        $ver = (& $exe -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>$null | Select-Object -First 1)
        if($LASTEXITCODE -ne 0 -or -not $ver) { continue }
        if((([string]$ver).Trim()) -notmatch '^3\.12\.') { continue }
        if(-not (Test-Path -LiteralPath $wexe -PathType Leaf)) { $wexe = $exe }
        return @{ python=$exe; pythonw=$wexe; version=(([string]$ver).Trim()) }
      } catch { }
    }
    return $null
  }

  $resolvedPair = Resolve-SrPythonPair $candidateList

  if($null -eq $resolvedPair) {
    Write-SrLog 'Python 3.12 real nao encontrado. Instalando Python oficial por usuario (ZERO ADMIN).'
    $installer = Join-Path $CacheDir 'python-3.12.10-amd64.exe'
    if(-not (Test-Path $installer)) {
      Invoke-SrDownload 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' $installer 300 3
    }

    # So executa o instalador oficial se a assinatura digital for valida.
    $sig = Get-AuthenticodeSignature -LiteralPath $installer
    if($sig.Status -ne 'Valid') {
      throw ('Python installer authenticity check failed. Signature status: ' + $sig.Status)
    }
    Write-SrLog ('Python installer signature valid: ' + $sig.SignerCertificate.Subject)

    # Usa o destino padrao por usuario. O Launcher anterior usava TargetDir privado e
    # podia receber exit code 0 sem encontrar python.exe na pasta esperada.
    $arguments = @(
      '/quiet',
      'InstallAllUsers=0',
      'Include_launcher=0',
      'InstallLauncherAllUsers=0',
      'PrependPath=0',
      'AppendPath=0',
      'AssociateFiles=0',
      'Shortcuts=0',
      'Include_test=0',
      'Include_doc=0',
      'Include_dev=0',
      'Include_debug=0',
      'Include_symbols=0',
      'Include_tcltk=1',
      'Include_pip=1'
    )
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru
    Write-SrLog ('Python installer exit code: ' + $process.ExitCode)
    if($process.ExitCode -ne 0) {
      throw ('Python per-user installation failed. Exit code: ' + $process.ExitCode)
    }

    $postInstall = New-Object 'System.Collections.Generic.List[string]'
    foreach($c in @(
      (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe'),
      (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
    )) {
      if(Test-Path -LiteralPath $c -PathType Leaf) { $postInstall.Add($c) }
    }
    $resolvedPair = Resolve-SrPythonPair $postInstall
    if($null -eq $resolvedPair) {
      throw ('Python installer returned success (exit code 0), but Python 3.12 could not be located. Check antivirus quarantine and ' + $LogDir)
    }
  }

  $pythonExe = [string]$resolvedPair.python
  $pythonwExe = [string]$resolvedPair.pythonw
  Write-SrLog ('Using Python ' + [string]$resolvedPair.version + ': ' + $pythonExe)

  $requirementsPath = Join-Path $AppDir 'requirements.txt'
  if(Test-Path $requirementsPath) {
    $requirementsHash = Get-SrSha256 $requirementsPath
    $marker = Join-Path $RuntimeDir 'srstudio_requirements.sha256'
    $markerValue = $requirementsHash + '|' + $pythonExe
    $installedMarker = ''
    if(Test-Path $marker) { try { $installedMarker = (Get-Content -Raw -LiteralPath $marker).Trim() } catch { } }
    if($installedMarker -ne $markerValue) {
      Write-SrLog 'Installing/updating SR Studio Python dependencies.'
      $pipLog = Join-Path $LogDir 'pip_runtime.log'
      $pipErr = $pipLog + '.err'
      $pipArgs = @('-m','pip','install','--disable-pip-version-check','--no-warn-script-location','--upgrade','-r',$requirementsPath)
      $proc = Start-Process -FilePath $pythonExe -ArgumentList $pipArgs -Wait -PassThru -RedirectStandardOutput $pipLog -RedirectStandardError $pipErr
      if($proc.ExitCode -ne 0) { throw ('Python dependencies failed to install. See ' + $pipErr) }
      [IO.File]::WriteAllText($marker,$markerValue,(New-Object Text.UTF8Encoding($false)))
      Write-SrLog 'SR Studio Python dependencies are ready.'
    }
  }
  return $pythonwExe
}

function Start-SrDesktop'''


def patch_launcher() -> bytes:
    text = LAUNCHER.read_text(encoding="utf-8-sig")
    if "4.0.1-hybrid.base2.6" not in text:
        text = text.replace(
            "$LauncherVersion = '4.0.1-hybrid.base2.5'",
            "$LauncherVersion = '4.0.1-hybrid.base2.6'",
            1,
        )
    pattern = r"function Ensure-SrPythonRuntime \{.*?\n\}\n\nfunction Start-SrDesktop"
    updated, count = re.subn(pattern, lambda _m: NEW_FUNC, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"Ensure-SrPythonRuntime replacement count={count}")
    data = ("\ufeff" + updated.lstrip("\ufeff")).encode("utf-8")
    LAUNCHER.write_bytes(data)
    return data


def update_manifest(data: bytes) -> None:
    now = datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")
    manifest = {
        "format": "SRSTUDIO_LAUNCHER_MANIFEST_1",
        "product": "SR Studio Launcher",
        "version": "4.0.1-hybrid.base2.6",
        "published_at": now,
        "files": [
            {
                "path": "SRStudioLauncher.ps1",
                "source": "launcher/files/SRStudioLauncher.ps1",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_clean_installer() -> tuple[Path, Path]:
    DIST.mkdir(exist_ok=True)
    cmd = DIST / "SR_STUDIO_SETUP_4.0.16_STABLE_LIMPO.cmd"
    zip_path = DIST / "SR_STUDIO_SETUP_4.0.16_STABLE_LIMPO.zip"
    text = r'''@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title SR Studio 4.0.16 - Instalador Limpo
set "ROOT=%LOCALAPPDATA%\SRStudio"
set "LAUNCHER=%ROOT%\Launcher"
set "CONFIG=%ROOT%\Config"
set "LOGS=%ROOT%\Logs"
set "RAW=https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main"

echo ============================================================
echo         SR STUDIO 4.0.16 - INSTALADOR LIMPO
echo ============================================================
echo.
echo Sem payload Base64. Componentes baixados do repositorio oficial.
echo.
where curl.exe >nul 2>&1 || (echo ERRO: curl.exe nao encontrado no Windows.& pause & exit /b 10)
mkdir "%LAUNCHER%" "%CONFIG%" "%LOGS%" >nul 2>&1

echo [1/4] Baixando Bootstrap oficial...
curl.exe -fL --retry 3 "%RAW%/launcher/files/SRStudioBootstrap.ps1" -o "%LAUNCHER%\SRStudioBootstrap.ps1" || (echo Falha no Bootstrap.& pause & exit /b 11)

echo [2/4] Baixando Launcher oficial...
curl.exe -fL --retry 3 "%RAW%/launcher/files/SRStudioLauncher.ps1" -o "%LAUNCHER%\SRStudioLauncher.ps1" || (echo Falha no Launcher.& pause & exit /b 12)

echo [3/4] Preparando configuracao Stable...
>"%CONFIG%\launcher.json" echo {
>>"%CONFIG%\launcher.json" echo   "schema": 3,
>>"%CONFIG%\launcher.json" echo   "channel": "stable",
>>"%CONFIG%\launcher.json" echo   "auto_update": true,
>>"%CONFIG%\launcher.json" echo   "repair_on_start": true,
>>"%CONFIG%\launcher.json" echo   "full_repair_every_days": 7,
>>"%CONFIG%\launcher.json" echo   "allow_offline": true,
>>"%CONFIG%\launcher.json" echo   "remote_manifest_base": "https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main",
>>"%CONFIG%\launcher.json" echo   "local_repository": "",
>>"%CONFIG%\launcher.json" echo   "entrypoint": "SR_Studio_Gerador.py",
>>"%CONFIG%\launcher.json" echo   "python_command": "",
>>"%CONFIG%\launcher.json" echo   "encartes_cloud_url": "http://127.0.0.1:3000",
>>"%CONFIG%\launcher.json" echo   "keep_backups": 3,
>>"%CONFIG%\launcher.json" echo   "connect_timeout_seconds": 15,
>>"%CONFIG%\launcher.json" echo   "download_timeout_seconds": 300,
>>"%CONFIG%\launcher.json" echo   "download_retries": 3,
>>"%CONFIG%\launcher.json" echo   "auto_update_launcher": true
>>"%CONFIG%\launcher.json" echo }

>"%ROOT%\ABRIR_SR_STUDIO.cmd" echo @echo off
>>"%ROOT%\ABRIR_SR_STUDIO.cmd" echo "%%SystemRoot%%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -File "%%LOCALAPPDATA%%\SRStudio\Launcher\SRStudioBootstrap.ps1"
copy /y "%ROOT%\ABRIR_SR_STUDIO.cmd" "%USERPROFILE%\Desktop\SR Studio.cmd" >nul 2>&1

echo [4/4] Instalando/atualizando o SR Studio e preparando Python...
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -File "%LAUNCHER%\SRStudioBootstrap.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo A instalacao encontrou um erro. Codigo: %RC%
  echo Envie os arquivos de %%LOCALAPPDATA%%\SRStudio\Logs para diagnostico.
  pause
  exit /b %RC%
)

echo.
echo SR Studio instalado com sucesso.
exit /b 0
'''
    cmd.write_text(text, encoding="utf-8", newline="\r\n")
    raw = cmd.read_text(encoding="utf-8")
    forbidden = ["FromBase64String", "::BEGIN_", "-ExecutionPolicy Bypass"]
    for token in forbidden:
        if token in raw:
            raise SystemExit(f"Forbidden heuristic token in clean installer: {token}")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(cmd, cmd.name)
    return cmd, zip_path


if __name__ == "__main__":
    data = patch_launcher()
    update_manifest(data)
    cmd, zip_path = build_clean_installer()
    print("Launcher:", hashlib.sha256(data).hexdigest(), len(data))
    print("Installer:", hashlib.sha256(cmd.read_bytes()).hexdigest(), cmd.stat().st_size)
    print("ZIP:", hashlib.sha256(zip_path.read_bytes()).hexdigest(), zip_path.stat().st_size)
