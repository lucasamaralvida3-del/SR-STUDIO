from __future__ import annotations
import argparse, base64, hashlib, re, textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == 'installer' else Path.cwd()

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def wrap_b64(data: bytes) -> str:
    return '\n'.join(textwrap.wrap(base64.b64encode(data).decode('ascii'), 76))

def build(channel: str, output: Path) -> None:
    installer_t = (ROOT / 'installer' / 'SRStudioInstaller.ps1').read_text(encoding='utf-8-sig')
    bootstrap = (ROOT / 'launcher' / 'files' / 'SRStudioBootstrap.ps1').read_bytes()
    launcher = (ROOT / 'launcher' / 'files' / 'SRStudioLauncher.ps1').read_bytes()
    graphics2_updater = (ROOT / 'launcher' / 'files' / 'SRGraphics2Component.ps1').read_bytes()
    icon = (ROOT / 'staging' / 'logo_update' / 'source' / 'SR_Studio.ico').read_bytes()

    replacements = {
        '__BOOTSTRAP_SHA__': sha256(bootstrap),
        '__BOOTSTRAP_SIZE__': str(len(bootstrap)),
        '__LAUNCHER_SHA__': sha256(launcher),
        '__LAUNCHER_SIZE__': str(len(launcher)),
        '__GRAPHICS2_UPDATER_SHA__': sha256(graphics2_updater),
        '__GRAPHICS2_UPDATER_SIZE__': str(len(graphics2_updater)),
        '__ICON_SHA__': sha256(icon),
        '__ICON_SIZE__': str(len(icon)),
    }
    installer = installer_t
    for old, new in replacements.items():
        installer = installer.replace(old, new)
    if '__' in installer:
        leftovers = sorted(set(re.findall(r'__[A-Z0-9_]+__', installer)))
        if leftovers:
            raise SystemExit(f'Unresolved installer tokens: {leftovers}')
    installer_bytes = ('\ufeff' + installer.lstrip('\ufeff')).encode('utf-8')

    batch = rf'''@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title SR Studio 4.0.16 - Instalador Zero Admin
set "SR_SETUP_SELF=%~f0"
set "SR_SETUP_TEMP=%TEMP%\SRStudioSetup_%RANDOM%_%RANDOM%"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "SR_SETUP_CHANNEL={channel}"
set "SR_SETUP_NOLAUNCH="
if /I "%~1"=="stable" set "SR_SETUP_CHANNEL=stable"
if /I "%~1"=="beta" set "SR_SETUP_CHANNEL=beta"
if /I "%~1"=="--no-launch" set "SR_SETUP_NOLAUNCH=-NoLaunch"
if /I "%~2"=="--no-launch" set "SR_SETUP_NOLAUNCH=-NoLaunch"

if not exist "%PS%" (
  echo Windows PowerShell nao foi encontrado.
  if not defined SR_SETUP_CI pause
  exit /b 10
)

mkdir "%SR_SETUP_TEMP%\payload" >nul 2>&1

"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $txt=[IO.File]::ReadAllText($env:SR_SETUP_SELF); function X([string]$n,[string]$d){{$m=[regex]::Match($txt,'(?s)::BEGIN_'+$n+'\r?\n(.*?)\r?\n::END_'+$n); if(-not $m.Success){{throw ('Payload ausente: '+$n)}}; $b=($m.Groups[1].Value -replace '\s',''); [IO.File]::WriteAllBytes($d,[Convert]::FromBase64String($b))}}; X 'INSTALLER' (Join-Path $env:SR_SETUP_TEMP 'SRStudioInstaller.ps1'); X 'BOOTSTRAP' (Join-Path $env:SR_SETUP_TEMP 'payload\SRStudioBootstrap.ps1'); X 'LAUNCHER' (Join-Path $env:SR_SETUP_TEMP 'payload\SRStudioLauncher.ps1'); X 'GRAPHICS2_UPDATER' (Join-Path $env:SR_SETUP_TEMP 'payload\SRGraphics2Component.ps1'); X 'ICON' (Join-Path $env:SR_SETUP_TEMP 'payload\SR_Studio.ico')"
if errorlevel 1 (
  echo Nao foi possivel preparar o instalador.
  rmdir /s /q "%SR_SETUP_TEMP%" >nul 2>&1
  if not defined SR_SETUP_CI pause
  exit /b 11
)

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%SR_SETUP_TEMP%\SRStudioInstaller.ps1" -Channel "%SR_SETUP_CHANNEL%" %SR_SETUP_NOLAUNCH%
set "RC=%ERRORLEVEL%"
rmdir /s /q "%SR_SETUP_TEMP%" >nul 2>&1
if not "%RC%"=="0" (
  echo.
  echo A instalacao nao foi concluida. Codigo: %RC%
  if not defined SR_SETUP_CI pause
)
exit /b %RC%
'''
    payloads = [
        ('INSTALLER', installer_bytes),
        ('BOOTSTRAP', bootstrap),
        ('LAUNCHER', launcher),
        ('GRAPHICS2_UPDATER', graphics2_updater),
        ('ICON', icon),
    ]
    parts = [batch.rstrip('\n')]
    for name, data in payloads:
        parts.append(f'::BEGIN_{name}\n{wrap_b64(data)}\n::END_{name}')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(parts) + '\n', encoding='utf-8', newline='\r\n')
    print(f'Built {output} ({output.stat().st_size} bytes) default_channel={channel}')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--channel', choices=['stable','beta'], default='stable')
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    build(args.channel, args.output)
