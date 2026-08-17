param(
  [switch]$FullRepair
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$SrRoot = Join-Path $env:LOCALAPPDATA 'SRStudio'
$AppDir = Join-Path $SrRoot 'App'
$CacheDir = Join-Path $SrRoot 'Cache'
$ConfigDir = Join-Path $SrRoot 'Config'
$StageDir = Join-Path $SrRoot 'Staging'
$LogDir = Join-Path $SrRoot 'Logs'
$InstallDir = Join-Path $AppDir 'Graphics2Host'
$PreviousDir = Join-Path $AppDir 'Graphics2Host.previous'
$RuntimeManifestName = 'graphics2-host-runtime.json'
$RuntimeManifestSchema = 'srstudio/graphics2-host-runtime-1'
$InstallReceiptName = 'graphics2-host-install.json'
$InstallReceiptSchema = 'srstudio/graphics2-host-install-1'
$LogFile = Join-Path $LogDir 'launcher.log'

foreach($dir in @($AppDir,$CacheDir,$ConfigDir,$StageDir,$LogDir)) {
  New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

function Write-G2Log([string]$Message) {
  $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] Graphics2Host · ' + $Message
  Write-Host $line
  Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Get-G2Property($Object,[string]$Name,$DefaultValue) {
  if($null -ne $Object -and ($Object.PSObject.Properties.Name -contains $Name)) { return $Object.$Name }
  return $DefaultValue
}

function Read-G2Json([string]$Path) {
  return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

function Save-G2Json($Object,[string]$Path) {
  $parent = Split-Path $Path -Parent
  if($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
  $json = $Object | ConvertTo-Json -Depth 40
  [IO.File]::WriteAllText($Path,$json,(New-Object Text.UTF8Encoding($false)))
}

function Get-G2Sha256([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Test-G2UrlAllowed([string]$Url) {
  try { $uri = New-Object Uri($Url) } catch { return $false }
  if($uri.Scheme -eq 'https') { return $true }
  if($uri.Scheme -eq 'http' -and ($uri.Host -eq '127.0.0.1' -or $uri.Host -eq 'localhost')) { return $true }
  return $false
}

function Invoke-G2Download([string]$Url,[string]$Destination,[int]$TimeoutSec=600,[int]$Retries=3) {
  if(-not (Test-G2UrlAllowed $Url)) { throw ('URL insegura do Graphics2Host: ' + $Url) }
  $parent = Split-Path $Destination -Parent
  if($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
  $last = $null
  for($attempt=1; $attempt -le $Retries; $attempt++) {
    try {
      Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
      Write-G2Log ('download ' + $attempt + '/' + $Retries + ': ' + $Url)
      Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec $TimeoutSec -Headers @{'Cache-Control'='no-cache'}
      return
    } catch {
      $last = $_
      Write-G2Log ('download falhou: ' + $_.Exception.Message)
      if($attempt -lt $Retries) { Start-Sleep -Seconds ([Math]::Min(4,$attempt)) }
    }
  }
  throw $last
}

function Resolve-G2SafePath([string]$Root,[string]$Relative) {
  if([string]::IsNullOrWhiteSpace($Relative)) { throw 'Caminho vazio no catálogo Graphics2Host.' }
  if([IO.Path]::IsPathRooted($Relative)) { throw ('Caminho absoluto rejeitado: ' + $Relative) }
  if($Relative -match '(^|[\\/])\.\.([\\/]|$)') { throw ('Path traversal rejeitado: ' + $Relative) }
  $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\\')
  $candidate = [IO.Path]::GetFullPath((Join-Path $rootFull ($Relative.Replace('/','\\'))))
  $prefix = $rootFull + '\\'
  if(-not $candidate.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) {
    throw ('Arquivo sai da pasta Graphics2Host: ' + $Relative)
  }
  return $candidate
}

function Assert-G2Runtime([string]$Root,[string]$ExpectedVersion,[bool]$Full) {
  $rootFull = [IO.Path]::GetFullPath($Root)
  $manifestPath = Join-Path $rootFull $RuntimeManifestName
  if(-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Manifesto de runtime Graphics2Host ausente.' }
  $manifest = Read-G2Json $manifestPath
  if([string](Get-G2Property $manifest 'schema' '') -ne $RuntimeManifestSchema) { throw 'Schema do runtime Graphics2Host inválido.' }
  $engineVersion = [string](Get-G2Property $manifest 'engine_version' '')
  if($ExpectedVersion -and $engineVersion -ne $ExpectedVersion) {
    throw ('Versão do host ' + $engineVersion + ' diverge da versão esperada ' + $ExpectedVersion + '.')
  }
  $exeRelative = [string](Get-G2Property $manifest 'executable' '')
  $exe = Resolve-G2SafePath $rootFull $exeRelative
  if(-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw ('Executável Graphics2Host ausente: ' + $exeRelative) }
  $expectedExeSize = [int64](Get-G2Property $manifest 'executable_size' 0)
  $expectedExeHash = ([string](Get-G2Property $manifest 'executable_sha256' '')).ToLowerInvariant()
  if($expectedExeSize -gt 0 -and (Get-Item -LiteralPath $exe).Length -ne $expectedExeSize) { throw 'Tamanho do executável Graphics2Host diverge.' }
  if(-not $expectedExeHash -or (Get-G2Sha256 $exe) -ne $expectedExeHash) { throw 'SHA-256 do executável Graphics2Host diverge.' }

  $files = @($manifest.files)
  if($files.Count -eq 0) { throw 'Catálogo Graphics2Host está vazio.' }
  if($Full) {
    $seen = @{}
    foreach($entry in $files) {
      $relative = [string](Get-G2Property $entry 'path' '')
      if($seen.ContainsKey($relative)) { throw ('Entrada duplicada no catálogo Graphics2Host: ' + $relative) }
      $seen[$relative] = $true
      $candidate = Resolve-G2SafePath $rootFull $relative
      if(-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw ('Arquivo Graphics2Host ausente: ' + $relative) }
      $expectedSize = [int64](Get-G2Property $entry 'size' 0)
      $expectedHash = ([string](Get-G2Property $entry 'sha256' '')).ToLowerInvariant()
      if((Get-Item -LiteralPath $candidate).Length -ne $expectedSize) { throw ('Tamanho divergente: ' + $relative) }
      if(-not $expectedHash -or (Get-G2Sha256 $candidate) -ne $expectedHash) { throw ('SHA-256 divergente: ' + $relative) }
    }

    $catalog = @{}
    foreach($entry in $files) { $catalog[[string]$entry.path] = $true }
    foreach($actual in @(Get-ChildItem -LiteralPath $rootFull -File -Recurse -ErrorAction Stop)) {
      if($actual.Name -eq $RuntimeManifestName -or $actual.Name -eq $InstallReceiptName) { continue }
      $relative = $actual.FullName.Substring($rootFull.Length).TrimStart('\\').Replace('\\','/')
      if(-not $catalog.ContainsKey($relative)) { throw ('Arquivo fora do catálogo Graphics2Host: ' + $relative) }
    }
  }
  return [ordered]@{
    version = $engineVersion
    executable = $exe
    executable_relative = $exeRelative
    executable_sha256 = $expectedExeHash
    files = $files.Count
    runtime_manifest_sha256 = Get-G2Sha256 $manifestPath
  }
}

function Resolve-G2ComponentManifest {
  $cfgPath = Join-Path $ConfigDir 'launcher.json'
  if(-not (Test-Path -LiteralPath $cfgPath)) { return $null }
  try { $cfg = Read-G2Json $cfgPath } catch { return $null }
  $channel = [string](Get-G2Property $cfg 'channel' 'stable')
  if($channel -ne 'stable' -and $channel -ne 'beta') { $channel = 'stable' }
  $remoteBase = [string](Get-G2Property $cfg 'remote_manifest_base' '')
  $localRepository = [Environment]::ExpandEnvironmentVariables([string](Get-G2Property $cfg 'local_repository' ''))
  $manifestPath = Join-Path $StageDir 'graphics2-component-manifest.json'
  $sourceKind = ''
  $sourceBase = ''

  if($remoteBase -and (Test-G2UrlAllowed $remoteBase)) {
    try {
      $url = $remoteBase.TrimEnd('/') + '/' + $channel + '/manifest.json?ts=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
      Invoke-G2Download $url $manifestPath 30 2
      $sourceKind = 'remote'
      $sourceBase = $remoteBase.TrimEnd('/') + '/' + $channel
    } catch {
      Write-G2Log ('manifesto online indisponível: ' + $_.Exception.Message)
    }
  }
  if(-not $sourceKind -and $localRepository) {
    $localManifest = Join-Path $localRepository ($channel + '\\manifest.json')
    if(Test-Path -LiteralPath $localManifest -PathType Leaf) {
      Copy-Item -LiteralPath $localManifest -Destination $manifestPath -Force
      $sourceKind = 'local'
      $sourceBase = Join-Path $localRepository $channel
    }
  }
  if(-not $sourceKind) {
    $cached = Join-Path $CacheDir 'last_manifest.json'
    if(Test-Path -LiteralPath $cached -PathType Leaf) {
      Copy-Item -LiteralPath $cached -Destination $manifestPath -Force
      $sourceKind = 'cached'
    } else { return $null }
  }

  try { $manifest = Read-G2Json $manifestPath } catch { return $null }
  $component = Get-G2Property $manifest 'graphics2_host' $null
  if($null -eq $component -or -not [bool](Get-G2Property $component 'enabled' $false)) { return $null }
  return [ordered]@{ component=$component; kind=$sourceKind; base=$sourceBase; channel=$channel }
}

function Resolve-G2BundleSource($Resolved,[string]$Destination) {
  $component = $Resolved.component
  $absoluteUrl = [string](Get-G2Property $component 'url' '')
  $relativeSource = [string](Get-G2Property $component 'source' '')
  if($Resolved.kind -eq 'remote') {
    $url = $absoluteUrl
    if(-not $url -and $relativeSource) { $url = $Resolved.base.TrimEnd('/') + '/' + ($relativeSource -replace '\\','/') }
    if(-not $url) { throw 'Manifesto Graphics2Host não informou url/source.' }
    Invoke-G2Download $url $Destination 900 3
    return $url
  }
  if($Resolved.kind -eq 'local') {
    if(-not $relativeSource) { throw 'Manifesto local Graphics2Host não informou source.' }
    $sourcePath = Join-Path $Resolved.base ($relativeSource.Replace('/','\\'))
    if(-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw ('Bundle local Graphics2Host ausente: ' + $sourcePath) }
    Copy-Item -LiteralPath $sourcePath -Destination $Destination -Force
    return $sourcePath
  }
  throw 'Modo offline não possui bundle Graphics2Host disponível para reinstalação.'
}

function Find-G2ExtractedRoot([string]$ExtractDir,[string]$MemberPrefix) {
  if($MemberPrefix) {
    $candidate = Join-Path $ExtractDir ($MemberPrefix.Trim('/').Replace('/','\\'))
    if(Test-Path -LiteralPath (Join-Path $candidate $RuntimeManifestName) -PathType Leaf) { return $candidate }
  }
  if(Test-Path -LiteralPath (Join-Path $ExtractDir $RuntimeManifestName) -PathType Leaf) { return $ExtractDir }
  $matches = @(Get-ChildItem -LiteralPath $ExtractDir -Filter $RuntimeManifestName -File -Recurse -ErrorAction SilentlyContinue)
  if($matches.Count -eq 1) { return $matches[0].Directory.FullName }
  if($matches.Count -eq 0) { throw 'Bundle Graphics2Host não contém manifesto de runtime.' }
  throw 'Bundle Graphics2Host contém mais de um runtime e não pode ser resolvido com segurança.'
}

function Install-G2Component($Resolved) {
  $component = $Resolved.component
  $required = [bool](Get-G2Property $component 'required' $false)
  $expectedVersion = [string](Get-G2Property $component 'engine_version' '')
  if(-not $expectedVersion) { throw 'Manifesto Graphics2Host não informou engine_version.' }

  if(Test-Path -LiteralPath $InstallDir -PathType Container) {
    try {
      $current = Assert-G2Runtime $InstallDir $expectedVersion ([bool]$FullRepair)
      Write-G2Log ('runtime atual validado · ' + [string]$current.version + ' · ' + [string]$current.files + ' arquivo(s).')
      return
    } catch {
      Write-G2Log ('runtime instalado precisa de reparo/upgrade: ' + $_.Exception.Message)
    }
  }

  if($Resolved.kind -eq 'cached') {
    $message = 'Graphics2Host precisa de instalação/reparo, mas o Launcher está offline.'
    if($required) { throw $message }
    Write-G2Log ('opcional adiado · ' + $message)
    return
  }

  $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
  $work = Join-Path $StageDir ('graphics2_' + $stamp + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
  $zip = Join-Path $work 'graphics2-host.zip'
  $extract = Join-Path $work 'extract'
  $staging = Join-Path $AppDir ('Graphics2Host.staging-' + [guid]::NewGuid().ToString('N').Substring(0,10))
  New-Item -ItemType Directory -Path $work -Force | Out-Null
  try {
    $sourceBundle = Resolve-G2BundleSource $Resolved $zip
    $expectedSize = [int64](Get-G2Property $component 'size' 0)
    $expectedHash = ([string](Get-G2Property $component 'sha256' '')).ToLowerInvariant()
    if($expectedSize -gt 0 -and (Get-Item -LiteralPath $zip).Length -ne $expectedSize) { throw 'Tamanho do ZIP Graphics2Host inválido.' }
    if(-not $expectedHash -or (Get-G2Sha256 $zip) -ne $expectedHash) { throw 'SHA-256 do ZIP Graphics2Host inválido.' }

    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $sourceRoot = Find-G2ExtractedRoot $extract ([string](Get-G2Property $component 'member_prefix' ''))
    $sourceReport = Assert-G2Runtime $sourceRoot $expectedVersion $true
    Write-G2Log ('bundle validado · ' + [string]$sourceReport.version + ' · ' + [string]$sourceReport.files + ' arquivo(s).')

    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $sourceRoot -Destination $staging -Recurse -Force
    $stageReport = Assert-G2Runtime $staging $expectedVersion $true
    $receipt = [ordered]@{
      schema = $InstallReceiptSchema
      engine_version = [string]$stageReport.version
      installed_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
      executable = [string]$stageReport.executable_relative
      executable_sha256 = [string]$stageReport.executable_sha256
      runtime_manifest_sha256 = [string]$stageReport.runtime_manifest_sha256
      files = [int]$stageReport.files
      source_bundle = [string]$sourceBundle
      installed_by = 'SRStudioBootstrap/Graphics2Component'
    }
    Save-G2Json $receipt (Join-Path $staging $InstallReceiptName)

    if(Test-Path -LiteralPath $InstallDir) {
      Remove-Item -LiteralPath $PreviousDir -Recurse -Force -ErrorAction SilentlyContinue
      Move-Item -LiteralPath $InstallDir -Destination $PreviousDir -Force
    }
    try {
      Move-Item -LiteralPath $staging -Destination $InstallDir -Force
      [void](Assert-G2Runtime $InstallDir $expectedVersion $true)
    } catch {
      Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
      if(Test-Path -LiteralPath $PreviousDir -PathType Container) { Move-Item -LiteralPath $PreviousDir -Destination $InstallDir -Force }
      throw
    }
    Write-G2Log ('instalação atômica concluída · ' + $expectedVersion + '. Feature flag permaneceu inalterada.')
  } finally {
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
  }
}

$resolved = Resolve-G2ComponentManifest
if($null -eq $resolved) {
  Write-G2Log 'nenhum componente opcional habilitado no manifesto atual.'
  return
}
$required = [bool](Get-G2Property $resolved.component 'required' $false)
try {
  Install-G2Component $resolved
  return
} catch {
  if($required) {
    Write-G2Log ('ERRO obrigatório: ' + $_.Exception.Message)
    throw
  }
  Write-G2Log ('aviso opcional: ' + $_.Exception.Message + ' · Desktop Core continuará normalmente.')
  return
}
