param(
  [switch]$RepairOnly,
  [switch]$NoLaunch,
  [switch]$FullRepair
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$BootstrapVersion = '4.0.1-hybrid.setup3'
$OfficialRepositoryBase = 'https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main'
$SrHomeRoot = Join-Path $env:LOCALAPPDATA 'SRStudio'
$CfgDir = Join-Path $SrHomeRoot 'Config'
$InstalledLauncherDir = Join-Path $SrHomeRoot 'Launcher'
$CacheDir = Join-Path $SrHomeRoot 'Cache'
$LogDir = Join-Path $SrHomeRoot 'Logs'
foreach($dirPath in @($CfgDir,$InstalledLauncherDir,$CacheDir,$LogDir)) {
  New-Item -ItemType Directory -Force -Path $dirPath | Out-Null
}

$BootstrapLog = Join-Path $LogDir 'bootstrap.log'
function Write-BootLog([string]$Message) {
  $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
  Write-Host $line
  Add-Content -LiteralPath $BootstrapLog -Value $line -Encoding UTF8
}
function Get-BootSha([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}
function Read-BootJson([string]$Path) {
  return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}
function Download-BootFile([string]$Url,[string]$Destination,[int]$Retries=3) {
  $parentDir = Split-Path $Destination -Parent
  if($parentDir) { New-Item -ItemType Directory -Force -Path $parentDir | Out-Null }
  $last = $null
  for($attempt=1; $attempt -le $Retries; $attempt++) {
    try {
      if(Test-Path $Destination) { Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue }
      Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 45 -Headers @{'Cache-Control'='no-cache'}
      return
    } catch {
      $last = $_
      Write-BootLog ('Download ' + $attempt + '/' + $Retries + ' failed: ' + $_.Exception.Message)
      if($attempt -lt $Retries) { Start-Sleep -Seconds $attempt }
    }
  }
  throw $last
}
function Test-BootScriptSyntax([string]$Path) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors) | Out-Null
  if($errors -and $errors.Count -gt 0) {
    throw ('Launcher PowerShell syntax is invalid: ' + $errors[0].Message)
  }
}
function Sync-OnlineLauncher([string]$BaseUrl) {
  $manifestTemp = Join-Path $CacheDir 'launcher_manifest.json'
  Download-BootFile ($BaseUrl.TrimEnd('/') + '/manifests/launcher.json') $manifestTemp
  $manifest = Read-BootJson $manifestTemp
  if(([string]$manifest.format -ne 'SRSTUDIO_LAUNCHER_MANIFEST_1') -and ([string]$manifest.format -ne 'SRSTUDIO_LAUNCHER_1')) {
    throw 'Online launcher manifest is not in a supported self-update format.'
  }
  if($null -eq $manifest.files -or @($manifest.files).Count -eq 0) {
    throw 'Online launcher manifest contains no files.'
  }
  foreach($fileEntry in @($manifest.files)) {
    $relativePath = [string]$fileEntry.path
    $destination = Join-Path $InstalledLauncherDir ($relativePath.Replace('/','\'))
    $expectedHash = ([string]$fileEntry.sha256).ToLowerInvariant()
    $expectedSize = [int64]$fileEntry.size
    $needCopy = $true
    if(Test-Path $destination) {
      try {
        $needCopy = ((Get-BootSha $destination) -ne $expectedHash)
        if(-not $needCopy -and $expectedSize -gt 0) {
          $needCopy = ((Get-Item -LiteralPath $destination).Length -ne $expectedSize)
        }
      } catch { $needCopy = $true }
    }
    if($needCopy) {
      $tempFile = $destination + '.download'
      New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
      $url = $BaseUrl.TrimEnd('/') + '/' + ([string]$fileEntry.source -replace '\','/')
      Download-BootFile $url $tempFile
      if($expectedSize -gt 0 -and (Get-Item -LiteralPath $tempFile).Length -ne $expectedSize) {
        Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
        throw ('Invalid online launcher size: ' + $relativePath)
      }
      if((Get-BootSha $tempFile) -ne $expectedHash) {
        Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
        throw ('Invalid online launcher hash: ' + $relativePath)
      }
      Test-BootScriptSyntax $tempFile
      Move-Item -LiteralPath $tempFile -Destination $destination -Force
    }
  }
  return [string]$manifest.version
}

$CfgPath = Join-Path $CfgDir 'launcher.json'
$remoteBase = $OfficialRepositoryBase
if(Test-Path $CfgPath) {
  try {
    $cfg = Read-BootJson $CfgPath
    if($cfg.PSObject.Properties.Name -contains 'remote_manifest_base') {
      $configured = [string]$cfg.remote_manifest_base
      if($configured -and ($configured.StartsWith('https://') -or $configured.StartsWith('http://127.0.0.1') -or $configured.StartsWith('http://localhost'))) {
        $remoteBase = $configured
      }
    }
  } catch { }
}

$launcherToRun = Join-Path $InstalledLauncherDir 'SRStudioLauncher.ps1'
$onlineUpdated = $false
try {
  $onlineVersion = Sync-OnlineLauncher $remoteBase
  Write-BootLog ('Launcher synchronized online: ' + $onlineVersion)
  $onlineUpdated = $true
} catch {
  Write-BootLog ('Online launcher synchronization skipped: ' + $_.Exception.Message)
}

if(-not (Test-Path $launcherToRun)) {
  throw 'SRStudioLauncher.ps1 is missing. Reinstall SR Studio.'
}
Test-BootScriptSyntax $launcherToRun
if(-not $onlineUpdated) {
  Write-BootLog 'Using the installed Launcher fallback.'
}

# Setup 3: o host Qt do Graphics Engine 2 é um componente opcional e isolado.
# O updater lê `graphics2_host` do manifesto Stable/Beta. Se a propriedade não
# existe ou enabled=false, nada é instalado. O updater nunca ativa feature flag.
$graphics2Updater = Join-Path $InstalledLauncherDir 'SRGraphics2Component.ps1'
if(Test-Path -LiteralPath $graphics2Updater -PathType Leaf) {
  Test-BootScriptSyntax $graphics2Updater
  Write-BootLog 'Checking optional SR Graphics Engine 2 host component.'
  # O próprio componente trata falhas opcionais sem bloquear o Desktop Core.
  # Se um manifesto futuro marcar required=true, a exceção é propagada.
  & $graphics2Updater -FullRepair:$FullRepair
} else {
  Write-BootLog 'Graphics2Host component updater not installed; Desktop Core will continue normally.'
}

Write-BootLog ('Starting installed Launcher via Bootstrap ' + $BootstrapVersion + '.')
& $launcherToRun -RepairOnly:$RepairOnly -NoLaunch:$NoLaunch -FullRepair:$FullRepair
