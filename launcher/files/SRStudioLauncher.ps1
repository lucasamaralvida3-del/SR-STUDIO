param(
  [switch]$RepairOnly,
  [switch]$NoLaunch,
  [switch]$FullRepair
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# GitHub and Python.org require modern TLS on Windows PowerShell 5.1.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$LauncherVersion = '4.0.1-hybrid.base3.1'
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

# Base 3.0: acesso Beta universal, independente da versao do Core.
$BetaAccessLocalPath = Join-Path $CfgDir 'beta_access.json'
$BetaAccessCachePath = Join-Path $CacheDir 'beta_access_manifest.json'

function Get-SrTextSha256([string]$Text) {
  $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
  $sha = [Security.Cryptography.SHA256]::Create()
  try {
    return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()
  } finally { $sha.Dispose() }
}

function Normalize-SrBetaKey([string]$Key) {
  if(-not $Key) { return '' }
  return (($Key.ToUpperInvariant()) -replace '[^A-Z0-9]','')
}

function Get-SrBetaAccessManifest {
  $url = $officialRepositoryBase.TrimEnd('/') + '/manifests/beta_access.json?ts=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $tmp = Join-Path $StageDir 'beta_access_manifest.download.json'
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $tmp -TimeoutSec 20 -Headers @{'Cache-Control'='no-cache'}
    $m = Read-SrJson $tmp
    if([string]$m.format -ne 'SRSTUDIO_BETA_ACCESS_1') { throw 'Formato de acesso Beta invalido.' }
    Copy-Item -LiteralPath $tmp -Destination $BetaAccessCachePath -Force
    return $m
  } catch {
    Write-SrLog ('Validacao online da chave Beta indisponivel: ' + $_.Exception.Message)
    if(Test-Path -LiteralPath $BetaAccessCachePath) {
      $cached = Read-SrJson $BetaAccessCachePath
      if([string]$cached.format -eq 'SRSTUDIO_BETA_ACCESS_1') {
        Write-SrLog 'Usando manifesto de acesso Beta em cache.'
        return $cached
      }
    }
    throw 'Nao foi possivel validar o acesso ao canal Beta. Verifique a internet e tente novamente.'
  }
}

function Find-SrBetaKeyEntry($Manifest,[string]$Hash) {
  foreach($entry in @($Manifest.keys)) {
    $enabled = [bool](Get-SrProperty $entry 'enabled' $false)
    $expected = ([string](Get-SrProperty $entry 'sha256' '')).ToLowerInvariant()
    if($enabled -and $expected -and ($expected -eq $Hash.ToLowerInvariant())) { return $entry }
  }
  return $null
}

function Test-SrStoredBetaAccess($Manifest) {
  if(-not (Test-Path -LiteralPath $BetaAccessLocalPath)) { return $false }
  try {
    $local = Read-SrJson $BetaAccessLocalPath
    $hash = ([string](Get-SrProperty $local 'key_sha256' '')).ToLowerInvariant()
    if(-not $hash) { return $false }
    return ($null -ne (Find-SrBetaKeyEntry $Manifest $hash))
  } catch { return $false }
}

function Request-SrBetaAccess($Manifest) {
  try { Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction Stop } catch { throw 'Nao foi possivel abrir a tela de chave Beta.' }
  $message = "Digite sua CHAVE DE ACESSO BETA do SR Studio.`r`n`r`nA chave e universal e nao depende da versao da Beta."
  for($attempt=1; $attempt -le 3; $attempt++) {
    $entered = [Microsoft.VisualBasic.Interaction]::InputBox($message,'SR Studio - Acesso Beta','')
    if([string]::IsNullOrWhiteSpace($entered)) { throw 'Acesso ao canal Beta cancelado.' }
    $normalized = Normalize-SrBetaKey $entered
    $hash = Get-SrTextSha256 $normalized
    $entry = Find-SrBetaKeyEntry $Manifest $hash
    if($null -ne $entry) {
      $local = [ordered]@{
        format = 'SRSTUDIO_BETA_ACCESS_LOCAL_1'
        key_id = [string](Get-SrProperty $entry 'id' '')
        key_sha256 = $hash
        scope = 'beta'
        activated_at = (Get-Date).ToString('o')
      }
      Save-SrJson $local $BetaAccessLocalPath
      Write-SrLog ('Acesso Beta autorizado. Key ID: ' + [string]$local.key_id)
      return
    }
    $message = "Chave invalida. Tentativa $attempt de 3.`r`n`r`nDigite novamente a CHAVE DE ACESSO BETA."
  }
  throw 'Chave de acesso Beta invalida.'
}

function Assert-SrBetaAccess {
  if($channel -ne 'beta') { return }
  $manifest = Get-SrBetaAccessManifest
  if(Test-SrStoredBetaAccess $manifest) {
    Write-SrLog 'Acesso Beta universal ja autorizado neste computador.'
    return
  }
  Request-SrBetaAccess $manifest
}

if($channel -eq 'beta') { Assert-SrBetaAccess }

function Resolve-SrManifest {
  $remoteBase = [string](Get-SrProperty $cfg 'remote_manifest_base' '')
  $connectTimeout = [int](Get-SrProperty $cfg 'connect_timeout_seconds' 15)
  $retries = [int](Get-SrProperty $cfg 'download_retries' 3)
  if($remoteBase) {
    $baseUrl = $remoteBase.TrimEnd('/')
    if(-not (Test-SrUrlAllowed $baseUrl)) {
      throw 'Repository URL must use HTTPS. HTTP is accepted only for localhost tests.'
    }
    $url = $baseUrl + '/' + $channel + '/manifest.json?ts=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
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

function Repair-SrBundleManifest($Source,$Manifest) {
  if($null -eq $Manifest) { throw 'Repository manifest is empty.' }
  $bundleInfo = Get-SrProperty $Manifest 'bundle' $null
  $legacyUrl = [string](Get-SrProperty $Manifest 'bundle_url' '')
  if(-not $legacyUrl) { $legacyUrl = [string](Get-SrProperty $Manifest 'url' '') }
  $legacySha = ([string](Get-SrProperty $Manifest 'sha256' '')).ToLowerInvariant()
  $legacySize = [int64](Get-SrProperty $Manifest 'size' 0)
  $legacyPrefix = [string](Get-SrProperty $Manifest 'member_prefix' 'files/')
  if(-not $legacyPrefix) { $legacyPrefix = 'files/' }
  $changed = $false

  if($null -eq $bundleInfo) {
    if($legacyUrl -and $legacySha) {
      $bundleInfo = [pscustomobject][ordered]@{ url=$legacyUrl; sha256=$legacySha; size=$legacySize; member_prefix=$legacyPrefix }
      $Manifest | Add-Member -NotePropertyName bundle -NotePropertyValue $bundleInfo -Force
      $changed = $true
      Write-SrLog 'AUTO-REPAIR: manifesto bundle legado detectado; bloco bundle reconstruido automaticamente.'
    } else {
      throw 'Bundle manifest does not contain bundle information and cannot be repaired automatically.'
    }
  } else {
    $bundleUrlNow = [string](Get-SrProperty $bundleInfo 'url' '')
    $bundleShaNow = ([string](Get-SrProperty $bundleInfo 'sha256' '')).ToLowerInvariant()
    $bundleSizeNow = [int64](Get-SrProperty $bundleInfo 'size' 0)
    $bundlePrefixNow = [string](Get-SrProperty $bundleInfo 'member_prefix' '')
    if(-not $bundleUrlNow -and $legacyUrl) { $bundleInfo | Add-Member -NotePropertyName url -NotePropertyValue $legacyUrl -Force; $changed=$true }
    if(-not $bundleShaNow -and $legacySha) { $bundleInfo | Add-Member -NotePropertyName sha256 -NotePropertyValue $legacySha -Force; $changed=$true }
    if($bundleSizeNow -le 0 -and $legacySize -gt 0) { $bundleInfo | Add-Member -NotePropertyName size -NotePropertyValue $legacySize -Force; $changed=$true }
    if(-not $bundlePrefixNow) { $bundleInfo | Add-Member -NotePropertyName member_prefix -NotePropertyValue $legacyPrefix -Force; $changed=$true }
    if($changed) { Write-SrLog 'AUTO-REPAIR: bloco bundle incompleto foi completado usando campos de compatibilidade.' }
  }

  $finalUrl = [string](Get-SrProperty $bundleInfo 'url' '')
  $finalSha = ([string](Get-SrProperty $bundleInfo 'sha256' '')).ToLowerInvariant()
  if(-not $finalUrl -or -not (Test-SrUrlAllowed $finalUrl)) { throw 'Auto-repair could not produce a safe bundle URL.' }
  if($finalSha -and $finalSha.Length -ne 64) { throw 'Auto-repair found an invalid bundle SHA256.' }

  if($changed) {
    try {
      $repairPath = Join-Path $CacheDir 'last_manifest.repaired.json'
      Save-SrJson $Manifest $repairPath
      Write-SrLog ('AUTO-REPAIR: copia reparada salva em ' + $repairPath)
    } catch { Write-SrLog ('AUTO-REPAIR: nao foi possivel salvar copia local: ' + $_.Exception.Message) }
  }
  return $Manifest
}

function Apply-SrBundleManifest($Source,$Manifest) {
  $Manifest = Repair-SrBundleManifest $Source $Manifest
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
    if(-not (Test-Path $sourceRoot)) {
      $fallbackFiles = Join-Path $extractDir 'files'
      if(Test-Path $fallbackFiles) {
        $sourceRoot = $fallbackFiles
        $memberPrefix = 'files/'
        Write-SrLog 'AUTO-REPAIR: member_prefix invalido; pasta files/ detectada automaticamente.'
      } else {
        $topDirs = @(Get-ChildItem -LiteralPath $extractDir -Directory -ErrorAction SilentlyContinue)
        if($topDirs.Count -eq 1) {
          $sourceRoot = $topDirs[0].FullName
          Write-SrLog ('AUTO-REPAIR: member_prefix inferido automaticamente: ' + $topDirs[0].Name)
        } else { throw ('Bundle member prefix not found: ' + $memberPrefix) }
      }
    }

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
  New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

  $candidateList = New-Object 'System.Collections.Generic.List[string]'
  function Add-SrPythonCandidate([string]$Candidate,[string]$Origin='unknown') {
    if(-not $Candidate) { return }
    try { $expanded = Expand-SrEnv $Candidate } catch { $expanded = $Candidate }
    if(-not $expanded) { return }
    if($expanded -match '\\WindowsApps\\') { return }
    if((Test-Path -LiteralPath $expanded -PathType Leaf) -and -not $candidateList.Contains($expanded)) {
      $candidateList.Add($expanded)
      Write-SrLog ('Python candidate [' + $Origin + ']: ' + $expanded)
    }
  }

  function Add-SrRegistryPythonCandidates {
    $roots = @(
      'Registry::HKEY_CURRENT_USER\Software\Python\PythonCore',
      'Registry::HKEY_LOCAL_MACHINE\Software\Python\PythonCore',
      'Registry::HKEY_LOCAL_MACHINE\Software\Wow6432Node\Python\PythonCore'
    )
    foreach($root in $roots) {
      try {
        if(-not (Test-Path -LiteralPath $root)) { continue }
        foreach($tagKey in @(Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue)) {
          if(([string]$tagKey.PSChildName) -notmatch '^3\.12') { continue }
          $installKey = $tagKey.PSPath + '\InstallPath'
          if(-not (Test-Path -LiteralPath $installKey)) { continue }
          $item = Get-Item -LiteralPath $installKey -ErrorAction SilentlyContinue
          $props = Get-ItemProperty -LiteralPath $installKey -ErrorAction SilentlyContinue
          $installDir = ''
          try { $installDir = [string]$item.GetValue('') } catch { }
          $exe = ''
          $wexe = ''
          if($props) {
            try { $exe = [string]$props.ExecutablePath } catch { }
            try { $wexe = [string]$props.WindowedExecutablePath } catch { }
          }
          if(-not $exe -and $installDir) { $exe = Join-Path $installDir 'python.exe' }
          if(-not $wexe -and $installDir) { $wexe = Join-Path $installDir 'pythonw.exe' }
          Add-SrPythonCandidate $exe ('registry ' + $tagKey.PSChildName)
          Add-SrPythonCandidate $wexe ('registry ' + $tagKey.PSChildName)
        }
      } catch {
        Write-SrLog ('Python registry scan skipped for ' + $root + ': ' + $_.Exception.Message)
      }
    }
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
        $tmpOut = Join-Path $LogDir 'python_candidate.out.log'
        $tmpErr = Join-Path $LogDir 'python_candidate.err.log'
        Remove-Item -LiteralPath $tmpOut,$tmpErr -Force -ErrorAction SilentlyContinue
        $probe = Join-Path $LogDir 'python_candidate_probe.py'
        [IO.File]::WriteAllText($probe,"import sys`nprint('%d.%d.%d' % sys.version_info[:3])`n",(New-Object Text.UTF8Encoding($false)))
        & $exe $probe 1> $tmpOut 2> $tmpErr
        $candidateExit = $LASTEXITCODE
        $ver = ''
        if(Test-Path $tmpOut) { $ver = (Get-Content -Raw -LiteralPath $tmpOut).Trim() }
        if($candidateExit -ne 0 -or -not $ver) {
          $errText=''
          if(Test-Path $tmpErr) { try { $errText=(Get-Content -Raw -LiteralPath $tmpErr).Trim() } catch { } }
          Write-SrLog ('Python candidate rejected. Exit=' + $candidateExit + ' Path=' + $exe + $(if($errText){' Error=' + $errText}else{''}))
          continue
        }
        if($ver -notmatch '^3\.12\.') { Write-SrLog ('Python candidate wrong version ' + $ver + ': ' + $exe); continue }
        if(-not (Test-Path -LiteralPath $wexe -PathType Leaf)) { $wexe = $exe }
        return @{ python=$exe; pythonw=$wexe; version=$ver }
      } catch {
        Write-SrLog ('Python candidate could not start: ' + $exe + ' / ' + $_.Exception.Message)
      }
    }
    return $null
  }

  # 1) Runtime portatil do proprio SR Studio.
  Add-SrPythonCandidate (Join-Path $pythonRoot 'pythonw.exe') 'SR runtime'
  Add-SrPythonCandidate (Join-Path $pythonRoot 'python.exe') 'SR runtime'

  # 2) Python configurado no launcher.
  Add-SrPythonCandidate ([string](Get-SrProperty $cfg 'python_command' '')) 'launcher config'

  # 3) Registro oficial do Python (PEP 514 / instalador oficial).
  Add-SrRegistryPythonCandidates

  # 4) Caminhos comuns e qualquer Python312/Python3.12 instalado por usuario/maquina.
  foreach($baseDir in @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
    $(if($env:ProgramFiles){$env:ProgramFiles}else{$null}),
    $(if(${env:ProgramFiles(x86)}){${env:ProgramFiles(x86)}}else{$null})
  )) {
    if(-not $baseDir -or -not (Test-Path -LiteralPath $baseDir)) { continue }
    try {
      foreach($exeFile in @(Get-ChildItem -LiteralPath $baseDir -Filter 'python.exe' -File -Recurse -Depth 3 -ErrorAction SilentlyContinue)) {
        if($exeFile.FullName -match '\\WindowsApps\\') { continue }
        Add-SrPythonCandidate $exeFile.FullName 'filesystem scan'
        $w = Join-Path $exeFile.DirectoryName 'pythonw.exe'
        Add-SrPythonCandidate $w 'filesystem scan'
      }
    } catch { }
  }

  foreach($cmdName in @('pythonw.exe','python.exe')) {
    try {
      $cmd = Get-Command $cmdName -ErrorAction SilentlyContinue
      if($cmd) { Add-SrPythonCandidate $cmd.Source 'PATH' }
    } catch { }
  }

  $resolvedPair = Resolve-SrPythonPair $candidateList
  $runtimeRequirementsHash = ''

  if($null -eq $resolvedPair) {
    Write-SrLog 'Python 3.12 utilizavel nao encontrado. Preparando runtime portatil oficial do SR Studio.'
    $runtimeManifestUrl = $officialRepositoryBase.TrimEnd('/') + '/runtime/manifest.json'
    $runtimeManifestPath = Join-Path $CacheDir 'python_runtime_manifest.json'
    Invoke-SrDownload $runtimeManifestUrl $runtimeManifestPath 60 3
    $runtimeManifest = Read-SrJson $runtimeManifestPath
    if([string]$runtimeManifest.format -ne 'SRSTUDIO_PYTHON_RUNTIME_1') { throw 'Manifesto do runtime Python invalido.' }
    if(([string]$runtimeManifest.python_version) -notmatch '^3\.12\.') { throw 'Versao Python do runtime nao suportada.' }
    $runtimeUrl = [string]$runtimeManifest.url
    if(-not (Test-SrUrlAllowed $runtimeUrl)) { throw 'URL insegura no runtime Python.' }
    $runtimeZip = Join-Path $CacheDir 'srstudio_python_runtime.zip'
    $expectedSize = [int64]$runtimeManifest.size
    $expectedHash = ([string]$runtimeManifest.sha256).ToLowerInvariant()

    $cacheOk = $false
    if(Test-Path -LiteralPath $runtimeZip -PathType Leaf) {
      try {
        $cacheOk = (((Get-Item -LiteralPath $runtimeZip).Length -eq $expectedSize) -and ((Get-SrSha256 $runtimeZip) -eq $expectedHash))
      } catch { $cacheOk = $false }
    }
    if($cacheOk) {
      Write-SrLog 'Reutilizando runtime Python ja baixado e validado no cache.'
    } else {
      Invoke-SrDownload $runtimeUrl $runtimeZip ([int](Get-SrProperty $cfg 'download_timeout_seconds' 600)) 3
    }
    if($expectedSize -gt 0 -and (Get-Item -LiteralPath $runtimeZip).Length -ne $expectedSize) { throw 'Tamanho invalido do runtime Python.' }
    if((Get-SrSha256 $runtimeZip) -ne $expectedHash) { throw 'SHA-256 invalido do runtime Python.' }
    Write-SrLog ('Runtime Python validado: ' + $expectedHash)

    # Remove Mark-of-the-Web do ZIP e dos binarios extraidos. Isto nao desativa antivirus.
    try { Unblock-File -LiteralPath $runtimeZip -ErrorAction SilentlyContinue } catch { }
    $runtimeStage = Join-Path $StageDir ('python_runtime_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    Remove-Item -LiteralPath $runtimeStage -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $runtimeStage -Force | Out-Null
    Expand-Archive -LiteralPath $runtimeZip -DestinationPath $runtimeStage -Force
    try { Get-ChildItem -LiteralPath $runtimeStage -File -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue } catch { }

    $stagePython = Join-Path $runtimeStage 'python.exe'
    if(-not (Test-Path -LiteralPath $stagePython -PathType Leaf)) { throw 'python.exe ausente no runtime portatil.' }
    foreach($dll in @('python312.dll','vcruntime140.dll','vcruntime140_1.dll')) {
      $dllPath=Join-Path $runtimeStage $dll
      Write-SrLog ('Runtime component ' + $dll + ': ' + $(if(Test-Path -LiteralPath $dllPath){'OK'}else{'AUSENTE'}))
    }

    $stageOut = Join-Path $LogDir 'portable_python_start.out.log'
    $stageErr = Join-Path $LogDir 'portable_python_start.err.log'
    Remove-Item -LiteralPath $stageOut,$stageErr -Force -ErrorAction SilentlyContinue
    try {
      $stageProbe = Join-Path $LogDir 'portable_python_start_probe.py'
      [IO.File]::WriteAllText($stageProbe,"import sys`nprint('%d.%d.%d' % sys.version_info[:3])`n",(New-Object Text.UTF8Encoding($false)))
      & $stagePython $stageProbe 1> $stageOut 2> $stageErr
      $stageExit = $LASTEXITCODE
    } catch {
      throw ('Runtime Python portatil nao conseguiu iniciar processo: ' + $_.Exception.Message)
    }
    $stageVersion=''
    if(Test-Path $stageOut) { try { $stageVersion=(Get-Content -Raw -LiteralPath $stageOut).Trim() } catch { } }
    $stageError=''
    if(Test-Path $stageErr) { try { $stageError=(Get-Content -Raw -LiteralPath $stageErr).Trim() } catch { } }
    Write-SrLog ('Portable Python startup exit=' + $stageExit + ' version=' + $stageVersion + $(if($stageError){' stderr=' + $stageError}else{''}))
    if($stageExit -ne 0 -or $stageVersion -notmatch '^3\.12\.') {
      throw ('Runtime Python portatil nao iniciou corretamente. Exit=' + $stageExit + $(if($stageError){' / ' + $stageError}else{''}))
    }

    $importOut = Join-Path $LogDir 'portable_python_imports.out.log'
    $importErr = Join-Path $LogDir 'portable_python_imports.err.log'
    Remove-Item -LiteralPath $importOut,$importErr -Force -ErrorAction SilentlyContinue
    $importProbe = Join-Path $LogDir 'portable_python_imports_probe.py'
    [IO.File]::WriteAllText($importProbe,"import tkinter, openpyxl, pypdf, PIL, numpy, cv2, tkinterdnd2`nprint('SR_RUNTIME_OK')`n",(New-Object Text.UTF8Encoding($false)))
    & $stagePython $importProbe 1> $importOut 2> $importErr
    $importExit = $LASTEXITCODE
    if($importExit -ne 0) {
      $importError=''
      if(Test-Path $importErr) { try { $importError=(Get-Content -Raw -LiteralPath $importErr).Trim() } catch { } }
      throw ('Runtime Python portatil esta incompleto. Exit=' + $importExit + $(if($importError){' / ' + $importError}else{''}))
    }

    Remove-Item -LiteralPath $pythonRoot -Recurse -Force -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $runtimeStage -Destination $pythonRoot -Force
    $runtimeRequirementsHash = ([string]$runtimeManifest.requirements_sha256).ToLowerInvariant()
    $resolvedPair = Resolve-SrPythonPair @((Join-Path $pythonRoot 'pythonw.exe'),(Join-Path $pythonRoot 'python.exe'))
    if($null -eq $resolvedPair) { throw 'Runtime Python foi extraido, mas nao pode ser iniciado depois da instalacao.' }
    Write-SrLog ('Runtime Python portatil pronto: ' + [string]$resolvedPair.version)
  }

  $pythonExe = [string]$resolvedPair.python
  $pythonwExe = [string]$resolvedPair.pythonw
  Write-SrLog ('Using Python ' + [string]$resolvedPair.version + ': ' + $pythonExe)

  $requirementsPath = Join-Path $AppDir 'requirements.txt'
  if(Test-Path $requirementsPath) {
    $requirementsHash = Get-SrSha256 $requirementsPath
    $marker = Join-Path $RuntimeDir 'srstudio_requirements.sha256'
    $markerValue = $requirementsHash + '|' + $pythonExe
    if($runtimeRequirementsHash -and $runtimeRequirementsHash -eq $requirementsHash) {
      [IO.File]::WriteAllText($marker,$markerValue,(New-Object Text.UTF8Encoding($false)))
    }
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
    Start-Process -FilePath $entry -WorkingDirectory $AppDir
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
    Start-Process -FilePath $pythonPath -ArgumentList @('"' + $entry + '"') -WorkingDirectory $AppDir
    return
  }
  Start-Process -FilePath $entry -WorkingDirectory $AppDir
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
