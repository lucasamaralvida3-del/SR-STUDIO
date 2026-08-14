param(
  [switch]$RepairOnly,
  [switch]$NoLaunch,
  [switch]$FullRepair
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# GitHub and Python.org require modern TLS on Windows PowerShell 5.1.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$LauncherVersion = '4.0.1-hybrid.base3.2'
$SrHomeRoot = Join-Path $env:LOCALAPPDATA 'SRStudio'
$AppDir      = Join-Path $SrHomeRoot 'App'
$DataDir     = Join-Path $SrHomeRoot 'Data'
$CacheDir    = Join-Path $SrHomeRoot 'Cache'
$CfgDir      = Join-Path $SrHomeRoot 'Config'
$StageDir    = Join-Path $SrHomeRoot 'Staging'
$BackupDir   = Join-Path $SrHomeRoot 'Backups'
$LogDir      = Join-Path $SrHomeRoot 'Logs'
$RuntimeDir  = Join-Path $SrHomeRoot 'Runtime'
$InstalledLauncherDir = Join-Path $SrHomeRoot 'Launcher'

foreach($dirPath in @($SrHomeRoot,$AppDir,$DataDir,$CacheDir,$CfgDir,$StageDir,$BackupDir,$LogDir,$RuntimeDir,$InstalledLauncherDir)) {
  New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
}

$LogFile = Join-Path $LogDir 'launcher.log'
$CfgPath = Join-Path $CfgDir 'launcher.json'
$InstalledPath = Join-Path $CfgDir 'installed.json'
$CachedManifestPath = Join-Path $CacheDir 'last_manifest.json'
$IntegrityPath = Join-Path $CfgDir 'integrity.json'
$MutexName = 'Local\SRStudioHybridLauncherMutex'
$launcherMutex = New-Object System.Threading.Mutex($false,$MutexName)
$hasMutex = $false

function Write-SrLog([string]$Message) {
  $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Message
  Write-Host $line
  Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Get-SrSha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Read-SrJson([string]$Path) {
  return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

function Save-SrJson($Object,[string]$Path) {
  $parentDir = Split-Path $Path -Parent
  if($parentDir) { New-Item -ItemType Directory -Path $parentDir -Force | Out-Null }
  $jsonText = $Object | ConvertTo-Json -Depth 30
  [IO.File]::WriteAllText($Path,$jsonText,(New-Object Text.UTF8Encoding($false)))
}

function Expand-SrEnv([string]$Value) {
  if(-not $Value) { return $Value }
  return [Environment]::ExpandEnvironmentVariables($Value)
}

function Get-SrProperty($Object,[string]$Name,$DefaultValue) {
  if($null -ne $Object -and ($Object.PSObject.Properties.Name -contains $Name)) {
    return $Object.$Name
  }
  return $DefaultValue
}

function Invoke-SrDownload([string]$Url,[string]$Destination,[int]$TimeoutSec=120,[int]$Retries=3) {
  $parentDir = Split-Path $Destination -Parent
  if($parentDir) { New-Item -ItemType Directory -Path $parentDir -Force | Out-Null }
  $lastError = $null
  for($attempt=1; $attempt -le $Retries; $attempt++) {
    try {
      if(Test-Path $Destination) { Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue }
      Write-SrLog ('Download ' + $attempt + '/' + $Retries + ': ' + $Url)
      Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec $TimeoutSec -Headers @{'Cache-Control'='no-cache'}
      return
    }
    catch {
      $lastError = $_
      Write-SrLog ('Download attempt failed: ' + $_.Exception.Message)
      if($attempt -lt $Retries) { Start-Sleep -Seconds ([Math]::Min(4,$attempt)) }
    }
  }
  throw $lastError
}

function Test-SrUrlAllowed([string]$Url) {
  try { $uri = New-Object Uri($Url) } catch { return $false }
  if($uri.Scheme -eq 'https') { return $true }
  if($uri.Scheme -eq 'http' -and ($uri.Host -eq '127.0.0.1' -or $uri.Host -eq 'localhost')) { return $true }
  return $false
}

if(-not (Test-Path $CfgPath)) {
  $localRepoCandidate = Join-Path $PSScriptRoot '..\repository'
  $localRepo = ''
  if(Test-Path $localRepoCandidate) { $localRepo = (Resolve-Path $localRepoCandidate).Path }
  $newCfg = [ordered]@{
    schema = 2
    channel = 'stable'
    auto_update = $true
    repair_on_start = $true
    full_repair_every_days = 7
    allow_offline = $true
    remote_manifest_base = 'https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main'
    local_repository = $localRepo
    entrypoint = 'SR_Studio_Gerador.py'
    python_command = ''
    encartes_cloud_url = 'http://127.0.0.1:3000'
    keep_backups = 3
    connect_timeout_seconds = 15
    download_timeout_seconds = 180
    download_retries = 3
    auto_update_launcher = $true
  }
  Save-SrJson $newCfg $CfgPath
  Write-SrLog 'Initial launcher configuration created.'
}

$cfg = Read-SrJson $CfgPath
# Base 2.1: migrate existing Base 2 configuration automatically to the official GitHub repository.
$officialRepositoryBase = 'https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main'
if(-not [string](Get-SrProperty $cfg 'remote_manifest_base' '')) {
  $cfg.remote_manifest_base = $officialRepositoryBase
  Save-SrJson $cfg $CfgPath
  Write-SrLog 'Official GitHub update repository configured automatically.'
}
$channel = [string](Get-SrProperty $cfg 'channel' 'stable')
if(($channel -ne 'stable') -and ($channel -ne 'beta')) { $channel = 'stable' }

function Resolve-SrManifest {
  $remoteBase = [string](Get-SrProperty $cfg 'remote_manifest_base' '')
  $connectTimeout = [int](Get-SrProperty $cfg 'connect_timeout_seconds' 15)
  $retries = [int](Get-SrProperty $cfg 'download_retries' 3)
  if($remoteBase) {
    $baseUrl = $remoteBase.TrimEnd('/')
    if(-not (Test-SrUrlAllowed $baseUrl)) {
      throw 'Repository URL must use HTTPS. HTTP is accepted only for localhost tests.'
    }
    $url = $baseUrl + '/' + $channel + '/manifest.json'
    $tmp = Join-Path $StageDir ('manifest_' + $channel + '.json')
    try {
      Write-SrLog ('Checking online repository: ' + $url)
      Invoke-SrDownload $url $tmp $connectTimeout $retries
      Copy-Item -LiteralPath $tmp -Destination $CachedManifestPath -Force
      return @{ kind='remote'; manifest=$tmp; base=($baseUrl + '/' + $channel); online=$true }
    }
    catch {
      Write-SrLog ('Online repository unavailable: ' + $_.Exception.Message)
      if([bool](Get-SrProperty $cfg 'allow_offline' $true) -and (Test-Path $CachedManifestPath) -and (Test-Path $AppDir)) {
        Write-SrLog 'Using cached manifest in offline mode.'
        return @{ kind='cached'; manifest=$CachedManifestPath; base=''; online=$false }
      }
    }
  }

  $repo = Expand-SrEnv ([string](Get-SrProperty $cfg 'local_repository' ''))
  if($repo) {
    $manifestPath = Join-Path $repo ($channel + '\\manifest.json')
    if(Test-Path $manifestPath) {
      return @{ kind='local'; manifest=$manifestPath; base=(Join-Path $repo $channel); online=$false }
    }
  }

  if([bool](Get-SrProperty $cfg 'allow_offline' $true) -and (Test-Path $CachedManifestPath) -and (Test-Path $AppDir)) {
    Write-SrLog 'No repository available. Starting from last known valid installation.'
    return @{ kind='cached'; manifest=$CachedManifestPath; base=''; online=$false }
  }

  throw 'No update repository is available and no cached installation can be used.'
}

function Get-SrRepositoryFile($Source,[string]$Relative,[string]$Destination) {
  $parentDir = Split-Path $Destination -Parent
  if($parentDir) { New-Item -ItemType Directory -Path $parentDir -Force | Out-Null }
  if($Source.kind -eq 'remote') {
    $url = $Source.base.TrimEnd('/') + '/' + ($Relative -replace '\\','/')
    $downloadTimeout = [int](Get-SrProperty $cfg 'download_timeout_seconds' 180)
    $retries = [int](Get-SrProperty $cfg 'download_retries' 3)
    Invoke-SrDownload $url $Destination $downloadTimeout $retries
  }
  elseif($Source.kind -eq 'local') {
    $sourcePath = Join-Path $Source.base ($Relative.Replace('/','\'))
    if(-not (Test-Path $sourcePath)) { throw ('Repository file missing: ' + $sourcePath) }
    Copy-Item -LiteralPath $sourcePath -Destination $Destination -Force
  }
  else {
    throw 'Offline cached manifest cannot download missing files.'
  }
}

function Get-SrInstalledState {
  if(Test-Path $InstalledPath) {
    try { return Read-SrJson $InstalledPath } catch { }
  }
  return $null
}

function Test-SrFullRepairDue {
  if($FullRepair -or $RepairOnly) { return $true }
  $days = [int](Get-SrProperty $cfg 'full_repair_every_days' 7)
  if($days -le 0) { return $false }
  $state = Get-SrInstalledState
  if($null -eq $state) { return $true }
  $lastFull = [string](Get-SrProperty $state 'last_full_repair' '')
  if(-not $lastFull) { return $true }
  try {
    $dt = [DateTime]::Parse($lastFull)
    return ((Get-Date) - $dt).TotalDays -ge $days
  }
  catch { return $true }
}

function Get-SrNeeds($Manifest,[bool]$FullCheck) {
  $needs = @()
  foreach($fileEntry in @($Manifest.files)) {
    $relativePath = [string]$fileEntry.path
    $destinationPath = Join-Path $AppDir ($relativePath.Replace('/','\'))
    $critical = [bool](Get-SrProperty $fileEntry 'critical' $true)
    $mustHash = $FullCheck -or $critical
    if(-not (Test-Path $destinationPath)) {
      $needs += $fileEntry
      continue
    }
    if($mustHash) {
      try {
        $expectedHash = ([string]$fileEntry.sha256).ToLowerInvariant()
        if((Get-SrSha256 $destinationPath) -ne $expectedHash) { $needs += $fileEntry }
      }
      catch { $needs += $fileEntry }
    }
  }
  return @($needs)
}

function Apply-SrManifest($Source,$Manifest) {
  $installedState = Get-SrInstalledState
  $installedVersion = ''
  if($installedState) { $installedVersion = [string](Get-SrProperty $installedState 'version' '') }
  $targetVersion = [string]$Manifest.version
  $fullCheck = Test-SrFullRepairDue
  if($installedVersion -ne $targetVersion) { $fullCheck = $true }

  $needs = @(Get-SrNeeds $Manifest $fullCheck)
  if($needs.Count -eq 0) {
    $totalFiles = @($Manifest.files).Count
    Write-SrLog ('Desktop Core verified: ' + $totalFiles + '/' + $totalFiles + ' files. Version ' + $targetVersion)
    $stateObj = [ordered]@{version=$targetVersion;channel=$channel;checked_at=(Get-Date).ToString('o');launcher_version=$LauncherVersion}
    if($fullCheck) { $stateObj.last_full_repair = (Get-Date).ToString('o') }
    elseif($installedState -and (Get-SrProperty $installedState 'last_full_repair' '')) { $stateObj.last_full_repair = [string]$installedState.last_full_repair }
    Save-SrJson $stateObj $InstalledPath
    return $false
  }

  if($Source.kind -eq 'cached') {
    Write-SrLog ('Offline mode: ' + $needs.Count + ' file(s) would need repair, but the current valid installation will be opened without downloading.')
    return $false
  }

  Write-SrLog ('Update/repair required: ' + $needs.Count + ' file(s). Target ' + $targetVersion)
  $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $stage = Join-Path $StageDir $stamp
  $backup = Join-Path $BackupDir $stamp
  New-Item -ItemType Directory -Path $stage -Force | Out-Null
  New-Item -ItemType Directory -Path $backup -Force | Out-Null

  try {
    $bundleInfo = Get-SrProperty $Manifest 'bundle' $null
    $bundleExtract = ''
    if($null -ne $bundleInfo -and $Source.kind -eq 'remote') {
      $bundleUrl = [string](Get-SrProperty $bundleInfo 'url' '')
      if(-not $bundleUrl -or -not (Test-SrUrlAllowed $bundleUrl)) { throw 'Invalid or unsafe bundle URL in repository manifest.' }
      $bundleZip = Join-Path $stage 'desktop_core_bundle.zip'
      Write-SrLog ('Downloading Desktop Core bundle: ' + $bundleUrl)
      Invoke-SrDownload $bundleUrl $bundleZip ([int](Get-SrProperty $cfg 'download_timeout_seconds' 180)) ([int](Get-SrProperty $cfg 'download_retries' 3))
      $bundleExpectedHash = ([string](Get-SrProperty $bundleInfo 'sha256' '')).ToLowerInvariant()
      if($bundleExpectedHash -and (Get-SrSha256 $bundleZip) -ne $bundleExpectedHash) { throw 'Desktop Core bundle failed SHA256 validation.' }
      $bundleExtract = Join-Path $stage 'bundle'
      Expand-Archive -LiteralPath $bundleZip -DestinationPath $bundleExtract -Force
    }

    $index = 0
    foreach($fileEntry in $needs) {
      $index++
      $relativePath = [string]$fileEntry.path
      Write-SrLog ('Preparing ' + $index + '/' + $needs.Count + ': ' + $relativePath)
      $stagePath = Join-Path $stage ('prepared\' + $relativePath.Replace('/','\'))
      New-Item -ItemType Directory -Path (Split-Path $stagePath -Parent) -Force | Out-Null
      if($bundleExtract) {
        $prefix = [string](Get-SrProperty $bundleInfo 'member_prefix' 'files/')
        $memberRelative = ($prefix.TrimEnd('/') + '/' + $relativePath).Replace('/','\')
        $bundleSource = Join-Path $bundleExtract $memberRelative
        if(-not (Test-Path $bundleSource)) { throw ('Bundle file missing: ' + $relativePath) }
        Copy-Item -LiteralPath $bundleSource -Destination $stagePath -Force
      }
      else {
        Get-SrRepositoryFile $Source ([string]$fileEntry.source) $stagePath
      }
      $actualHash = Get-SrSha256 $stagePath
      $expectedHash = ([string]$fileEntry.sha256).ToLowerInvariant()
      if($actualHash -ne $expectedHash) { throw ('Invalid SHA256 for: ' + $relativePath) }
      if((Get-SrProperty $fileEntry 'size' $null) -ne $null) {
        $expectedSize = [int64]$fileEntry.size
        if((Get-Item -LiteralPath $stagePath).Length -ne $expectedSize) { throw ('Invalid size for: ' + $relativePath) }
      }
    }

    foreach($fileEntry in $needs) {
      $relativePath = [string]$fileEntry.path
      $destinationPath = Join-Path $AppDir ($relativePath.Replace('/','\'))
      if(Test-Path $destinationPath) {
        $backupPath = Join-Path $backup ($relativePath.Replace('/','\'))
        New-Item -ItemType Directory -Path (Split-Path $backupPath -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $destinationPath -Destination $backupPath -Force
      }
    }

    foreach($fileEntry in $needs) {
      $relativePath = [string]$fileEntry.path
      $stagePath = Join-Path $stage ('prepared\' + $relativePath.Replace('/','\'))
      $destinationPath = Join-Path $AppDir ($relativePath.Replace('/','\'))
      New-Item -ItemType Directory -Path (Split-Path $destinationPath -Parent) -Force | Out-Null
      $tempDestination = $destinationPath + '.srnew'
      Copy-Item -LiteralPath $stagePath -Destination $tempDestination -Force
      if((Get-SrSha256 $tempDestination) -ne ([string]$fileEntry.sha256).ToLowerInvariant()) { throw ('Post-copy verification failed: ' + $relativePath) }
      Move-Item -LiteralPath $tempDestination -Destination $destinationPath -Force
    }

    if($Manifest.delete) {
      foreach($deleteEntry in @($Manifest.delete)) {
        $deletePath = Join-Path $AppDir ([string]$deleteEntry).Replace('/','\')
        if(Test-Path $deletePath) { Remove-Item -LiteralPath $deletePath -Recurse -Force }
      }
    }

    $stateObj = [ordered]@{version=$targetVersion;channel=$channel;updated_at=(Get-Date).ToString('o');checked_at=(Get-Date).ToString('o');last_full_repair=(Get-Date).ToString('o');launcher_version=$LauncherVersion}
    Save-SrJson $stateObj $InstalledPath
    Write-SrLog ('Update applied successfully: ' + $targetVersion)
  }
  catch {
    Write-SrLog ('Update failed: ' + $_.Exception.Message)
    if(Test-Path $backup) {
      Get-ChildItem -LiteralPath $backup -Recurse -File | ForEach-Object {
        $relativeBackup = $_.FullName.Substring($backup.Length).TrimStart('\')
        $restorePath = Join-Path $AppDir $relativeBackup
        New-Item -ItemType Directory -Path (Split-Path $restorePath -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $restorePath -Force
      }
      Write-SrLog 'Rollback completed.'
    }
    throw
  }
  finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
  }

  $keep = [int](Get-SrProperty $cfg 'keep_backups' 3)
  if($keep -lt 1) { $keep = 1 }
  Get-ChildItem -LiteralPath $BackupDir -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -Skip $keep | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
  return $true
}


function Get-SrIntegrityCatalog {
  if(Test-Path $IntegrityPath) {
    try { return Read-SrJson $IntegrityPath } catch { }
  }
  return $null
}

function New-SrIntegrityCatalog([string]$Root,[string]$Version) {
  $items = @()
  Get-ChildItem -LiteralPath $Root -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($Root.Length).TrimStart('\\').Replace('\\','/')
    $items += [ordered]@{ path=$relative; sha256=(Get-SrSha256 $_.FullName); size=$_.Length }
  }
  return [ordered]@{ version=$Version; created_at=(Get-Date).ToString('o'); files=$items }
}

function Test-SrIntegrityCatalog($Catalog) {
  if($null -eq $Catalog -or -not $Catalog.files) { return $false }
  foreach($fileEntry in @($Catalog.files)) {
    $relative = [string]$fileEntry.path
    $target = Join-Path $AppDir ($relative.Replace('/','\\'))
    if(-not (Test-Path $target)) { Write-SrLog ('Integrity: missing ' + $relative); return $false }
    try {
      if((Get-SrSha256 $target) -ne ([string]$fileEntry.sha256).ToLowerInvariant()) {
        Write-SrLog ('Integrity: changed ' + $relative)
        return $false
      }
    } catch { return $false }
  }
  return $true
}

function Apply-SrBundleManifest($Source,$Manifest) {
  $targetVersion = [string]$Manifest.version
  $installedState = Get-SrInstalledState
  $installedVersion = ''
  if($installedState) { $installedVersion = [string](Get-SrProperty $installedState 'version' '') }
  $needsInstall = ($installedVersion -ne $targetVersion) -or -not (Test-Path (Join-Path $AppDir ([string](Get-SrProperty $cfg 'entrypoint' 'SR_Studio_Gerador.py'))))

  if(-not $needsInstall -and (Test-SrFullRepairDue)) {
    $catalog = Get-SrIntegrityCatalog
    if(-not (Test-SrIntegrityCatalog $catalog)) { $needsInstall = $true }
    else { Write-SrLog ('Integrity catalog verified. Version ' + $targetVersion) }
  }

  if(-not $needsInstall) {
    Write-SrLog ('Desktop Core is current: ' + $targetVersion)
    return $false
  }

  if($Source.kind -eq 'cached') {
    Write-SrLog 'Offline mode: an update or repair is needed, but the server is unavailable. Opening the last local installation.'
    return $false
  }

  $bundleInfo = Get-SrProperty $Manifest 'bundle' $null
  if($null -eq $bundleInfo) { throw 'Bundle manifest does not contain bundle information.' }
  $bundleUrl = [string](Get-SrProperty $bundleInfo 'url' '')
  if(-not $bundleUrl -or -not (Test-SrUrlAllowed $bundleUrl)) { throw 'Invalid or unsafe bundle URL.' }
  $expectedBundleHash = ([string](Get-SrProperty $bundleInfo 'sha256' '')).ToLowerInvariant()
  $expectedBundleSize = [int64](Get-SrProperty $bundleInfo 'size' 0)
  $memberPrefix = [string](Get-SrProperty $bundleInfo 'member_prefix' 'files/')

  $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $stage = Join-Path $StageDir ('bundle_' + $stamp)
  $backup = Join-Path $BackupDir ('bundle_' + $stamp)
  New-Item -ItemType Directory -Path $stage -Force | Out-Null
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  try {
    $bundleZip = Join-Path $stage 'desktop_core.zip'
    Write-SrLog ('Downloading verified Desktop Core bundle: ' + $bundleUrl)
    Invoke-SrDownload $bundleUrl $bundleZip ([int](Get-SrProperty $cfg 'download_timeout_seconds' 180)) ([int](Get-SrProperty $cfg 'download_retries' 3))
    if($expectedBundleSize -gt 0 -and (Get-Item -LiteralPath $bundleZip).Length -ne $expectedBundleSize) { throw 'Desktop Core bundle size validation failed.' }
    if($expectedBundleHash -and (Get-SrSha256 $bundleZip) -ne $expectedBundleHash) { throw 'Desktop Core bundle SHA256 validation failed.' }

    $extractDir = Join-Path $stage 'extracted'
    Expand-Archive -LiteralPath $bundleZip -DestinationPath $extractDir -Force
    $sourceRoot = Join-Path $extractDir ($memberPrefix.Trim('/').Replace('/','\\'))
    if(-not (Test-Path $sourceRoot)) { throw ('Bundle member prefix not found: ' + $memberPrefix) }

    $newCatalog = New-SrIntegrityCatalog $sourceRoot $targetVersion
    if(@($newCatalog.files).Count -eq 0) { throw 'Desktop Core bundle contains no distributable files.' }
    Write-SrLog ('Bundle validated: ' + @($newCatalog.files).Count + ' files.')

    foreach($fileEntry in @($newCatalog.files)) {
      $relative = [string]$fileEntry.path
      $current = Join-Path $AppDir ($relative.Replace('/','\\'))
      if(Test-Path $current) {
        $backupPath = Join-Path $backup ($relative.Replace('/','\\'))
        New-Item -ItemType Directory -Path (Split-Path $backupPath -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $current -Destination $backupPath -Force
      }
    }

    foreach($fileEntry in @($newCatalog.files)) {
      $relative = [string]$fileEntry.path
      $from = Join-Path $sourceRoot ($relative.Replace('/','\\'))
      $to = Join-Path $AppDir ($relative.Replace('/','\\'))
      New-Item -ItemType Directory -Path (Split-Path $to -Parent) -Force | Out-Null
      $temp = $to + '.srnew'
      Copy-Item -LiteralPath $from -Destination $temp -Force
      if((Get-SrSha256 $temp) -ne ([string]$fileEntry.sha256).ToLowerInvariant()) { throw ('Post-copy integrity failed: ' + $relative) }
      Move-Item -LiteralPath $temp -Destination $to -Force
    }

    if($Manifest.delete) {
      foreach($deleteEntry in @($Manifest.delete)) {
        $deletePath = Join-Path $AppDir ([string]$deleteEntry).Replace('/','\\')
        if(Test-Path $deletePath) { Remove-Item -LiteralPath $deletePath -Recurse -Force }
      }
    }

    Save-SrJson $newCatalog $IntegrityPath
    $stateObj = [ordered]@{version=$targetVersion;channel=$channel;updated_at=(Get-Date).ToString('o');checked_at=(Get-Date).ToString('o');last_full_repair=(Get-Date).ToString('o');launcher_version=$LauncherVersion;distribution='bundle'}
    Save-SrJson $stateObj $InstalledPath
    Write-SrLog ('Bundle update applied successfully: ' + $targetVersion)
  }
  catch {
    Write-SrLog ('Bundle update failed: ' + $_.Exception.Message)
    if(Test-Path $backup) {
      Get-ChildItem -LiteralPath $backup -Recurse -File | ForEach-Object {
        $relativeBackup = $_.FullName.Substring($backup.Length).TrimStart('\\')
        $restorePath = Join-Path $AppDir $relativeBackup
        New-Item -ItemType Directory -Path (Split-Path $restorePath -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $restorePath -Force
      }
      Write-SrLog 'Rollback completed.'
    }
    throw
  }
  finally { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
  return $true
}

function Ensure-SrPythonRuntime {
  $pythonRoot = Join-Path $RuntimeDir 'python'
  $pythonExe = Join-Path $pythonRoot 'python.exe'
  $pythonwExe = Join-Path $pythonRoot 'pythonw.exe'
  if(-not (Test-Path $pythonExe) -or -not (Test-Path $pythonwExe)) {
    Write-SrLog 'Python runtime is not present. Preparing private per-user runtime (ZERO ADMIN).'
    New-Item -ItemType Directory -Path $pythonRoot -Force | Out-Null
    $installer = Join-Path $CacheDir 'python-3.12.10-amd64.exe'
    if(-not (Test-Path $installer)) {
      Invoke-SrDownload 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' $installer 300 3
    }
    $arguments = @(
      '/quiet',
      'InstallAllUsers=0',
      ('TargetDir=' + $pythonRoot),
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
    if($process.ExitCode -ne 0 -or -not (Test-Path $pythonExe)) {
      throw ('Private Python runtime installation failed. Exit code: ' + $process.ExitCode)
    }
    Write-SrLog 'Private Python runtime prepared successfully.'
  }

  $requirementsPath = Join-Path $AppDir 'requirements.txt'
  if(Test-Path $requirementsPath) {
    $requirementsHash = Get-SrSha256 $requirementsPath
    $marker = Join-Path $pythonRoot 'srstudio_requirements.sha256'
    $installedHash = ''
    if(Test-Path $marker) { try { $installedHash = (Get-Content -Raw -LiteralPath $marker).Trim() } catch { } }
    if($installedHash -ne $requirementsHash) {
      Write-SrLog 'Installing/updating SR Studio Python dependencies in the private runtime.'
      $pipLog = Join-Path $LogDir 'pip_runtime.log'
      $pipArgs = @('-m','pip','install','--disable-pip-version-check','--no-warn-script-location','--upgrade','-r',$requirementsPath)
      $proc = Start-Process -FilePath $pythonExe -ArgumentList $pipArgs -Wait -PassThru -RedirectStandardOutput $pipLog -RedirectStandardError ($pipLog + '.err')
      if($proc.ExitCode -ne 0) { throw ('Python dependencies failed to install. See ' + $pipLog + '.err') }
      [IO.File]::WriteAllText($marker,$requirementsHash,(New-Object Text.UTF8Encoding($false)))
      Write-SrLog 'SR Studio Python dependencies are ready.'
    }
  }
  return $pythonwExe
}

# SR5_BETA6_LAUNCH_GUARD
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
  $entry = Join-Path $AppDir ([string](Get-SrProperty $cfg 'entrypoint' 'SR_Studio_Gerador.py')).Replace('/','\')
  if(-not (Test-Path $entry)) {
    Write-SrLog ('Desktop Core entrypoint not found: ' + $entry)
    Start-Process -FilePath 'explorer.exe' -ArgumentList @($AppDir)
    throw 'Desktop Core entrypoint not found.'
  }
  $extension = [IO.Path]::GetExtension($entry).ToLowerInvariant()
  Write-SrLog ('Opening Desktop Core: ' + $entry)
  if($extension -eq '.exe') {
    Start-SrGuardedProcess $entry @() $AppDir
    return
  }
  if($extension -eq '.py') {
    $pythonPath = Ensure-SrPythonRuntime
    $configuredPython = [string](Get-SrProperty $cfg 'python_command' '')
    if($configuredPython) {
      $configuredCandidate = Expand-SrEnv $configuredPython
      $looksLikeStoreAlias = ($configuredCandidate -match '\\WindowsApps\\')
      if((Test-Path -LiteralPath $configuredCandidate -PathType Leaf) -and -not $looksLikeStoreAlias) {
        $pythonPath = $configuredCandidate
        Write-SrLog ('Using configured Python runtime: ' + $configuredCandidate)
      } else {
        Write-SrLog ('Ignoring invalid/Store Python alias and using the private SR Studio runtime: ' + $configuredCandidate)
      }
    }
    $portableCandidates = @(
      (Join-Path $RuntimeDir 'python\\pythonw.exe'),
      (Join-Path $AppDir 'runtime\\python\\pythonw.exe'),
      (Join-Path $RuntimeDir 'python\\python.exe'),
      (Join-Path $AppDir 'runtime\\python\\python.exe')
    )
    if(-not $pythonPath) {
      foreach($candidatePath in $portableCandidates) { if(Test-Path $candidatePath) { $pythonPath=$candidatePath; break } }
    }
    if(-not $pythonPath) {
      $pythonCommand = Get-Command pythonw.exe -ErrorAction SilentlyContinue
      if($pythonCommand) { $pythonPath=$pythonCommand.Source }
    }
    if(-not $pythonPath) {
      $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
      if($pythonCommand) { $pythonPath=$pythonCommand.Source }
    }
    if(-not $pythonPath) { throw 'Python runtime not found. The Stable repository must provide a portable runtime for a new computer.' }
    Start-SrGuardedProcess $pythonPath @('"' + $entry + '"') $AppDir
    return
  }
  Start-SrGuardedProcess $entry @() $AppDir
}

try {
  $hasMutex = $launcherMutex.WaitOne(0,$false)
  if(-not $hasMutex) { Write-SrLog 'Another SR Studio Launcher instance is already running.'; exit 5 }

  Write-SrLog ('SR Studio Launcher ' + $LauncherVersion + ' - channel ' + $channel)
  $source = Resolve-SrManifest
  $manifest = Read-SrJson $source.manifest
  $manifestFormat = [string]$manifest.format
  if(($manifestFormat -ne 'SRSTUDIO_HYBRID_MANIFEST_1') -and ($manifestFormat -ne 'SRSTUDIO_HYBRID_MANIFEST_2') -and ($manifestFormat -ne 'SRSTUDIO_HYBRID_BUNDLE_1')) { throw 'Incompatible repository manifest format.' }

  $minLauncher = [string](Get-SrProperty $manifest 'min_launcher_version' '')
  if($minLauncher) { Write-SrLog ('Repository minimum launcher: ' + $minLauncher + '. Current: ' + $LauncherVersion) }

  if([bool](Get-SrProperty $cfg 'auto_update' $true) -or [bool](Get-SrProperty $cfg 'repair_on_start' $true) -or $RepairOnly) {
    if($manifestFormat -eq 'SRSTUDIO_HYBRID_BUNDLE_1') { [void](Apply-SrBundleManifest $source $manifest) } else { [void](Apply-SrManifest $source $manifest) }
  }

  if($RepairOnly) { Write-SrLog 'Repair completed.'; exit 0 }
  if($NoLaunch) { exit 0 }
  Start-SrDesktop
}
catch {
  $errorMessage = $_.Exception.Message
  Write-SrLog ('ERROR: ' + $errorMessage)
  try {
    Add-Type -AssemblyName PresentationFramework -ErrorAction Stop
    $dialogText = 'SR Studio could not start.' + [Environment]::NewLine + [Environment]::NewLine + $errorMessage + [Environment]::NewLine + [Environment]::NewLine + 'Log: ' + $LogFile
    [System.Windows.MessageBox]::Show($dialogText,'SR Studio Launcher') | Out-Null
  }
  catch { Write-Host ('See log: ' + $LogFile) }
  exit 1
}
finally {
  if($hasMutex) { try { $launcherMutex.ReleaseMutex() | Out-Null } catch { } }
  $launcherMutex.Dispose()
}
