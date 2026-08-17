param(
  [ValidateSet('stable','beta')]
  [string]$Channel = 'stable',
  [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$InstallerVersion = '4.0.16-setup3'
$OfficialRepositoryBase = 'https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main'
$SrRoot = Join-Path $env:LOCALAPPDATA 'SRStudio'
$AppDir = Join-Path $SrRoot 'App'
$DataDir = Join-Path $SrRoot 'Data'
$CacheDir = Join-Path $SrRoot 'Cache'
$ConfigDir = Join-Path $SrRoot 'Config'
$LauncherDir = Join-Path $SrRoot 'Launcher'
$RuntimeDir = Join-Path $SrRoot 'Runtime'
$LogDir = Join-Path $SrRoot 'Logs'
$BackupDir = Join-Path $SrRoot 'Backups'
$StagingDir = Join-Path $SrRoot 'Staging'
$UninstallDir = Join-Path $SrRoot 'Uninstall'
$SetupLog = Join-Path $LogDir 'setup.log'
$PayloadDir = Join-Path $PSScriptRoot 'payload'

function Write-Setup([string]$Message) {
  $line = '[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $Message
  Write-Host $line
  if(Test-Path $LogDir) { Add-Content -LiteralPath $SetupLog -Value $line -Encoding UTF8 }
}
function Get-SetupSha([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}
function Save-SetupJson($Object,[string]$Path) {
  $text = $Object | ConvertTo-Json -Depth 30
  [IO.File]::WriteAllText($Path,$text,(New-Object Text.UTF8Encoding($false)))
}
function Test-PackageFile([string]$Name,[string]$Sha256,[int64]$Size) {
  $path = Join-Path $PayloadDir $Name
  if(-not (Test-Path $path)) { throw ('Arquivo do instalador ausente: ' + $Name) }
  if((Get-Item -LiteralPath $path).Length -ne $Size) { throw ('Tamanho invalido no instalador: ' + $Name) }
  if((Get-SetupSha $path) -ne $Sha256) { throw ('SHA-256 invalido no instalador: ' + $Name) }
  return $path
}
function Write-CmdFile([string]$Path,[string[]]$Lines) {
  $content = ($Lines -join "`r`n") + "`r`n"
  [IO.File]::WriteAllText($Path,$content,[Text.Encoding]::ASCII)
}
function New-SrShortcut([string]$Path,[string]$Arguments,[string]$Description) {
  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($Path)
  $shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $shortcut.Arguments = $Arguments
  $shortcut.WorkingDirectory = $AppDir
  $icon = Join-Path $LauncherDir 'SR_Studio.ico'
  if(Test-Path $icon) { $shortcut.IconLocation = $icon + ',0' }
  $shortcut.Description = $Description
  $shortcut.Save()
}
function Show-SetupError([string]$Message) {
  try {
    Add-Type -AssemblyName PresentationFramework -ErrorAction Stop
    [System.Windows.MessageBox]::Show($Message,'SR Studio - Instalador','OK','Error') | Out-Null
  } catch { }
}

try {
  Clear-Host
  Write-Host '============================================================'
  Write-Host '            SR STUDIO 4.0 - INSTALADOR ZERO ADMIN'
  Write-Host '============================================================'
  Write-Host ''
  Write-Host ('Canal: ' + $Channel.ToUpperInvariant())
  Write-Host ('Destino: ' + $SrRoot)
  Write-Host ''

  if($env:OS -ne 'Windows_NT') { throw 'Este instalador foi criado para Windows.' }
  if($PSVersionTable.PSVersion.Major -lt 5) { throw 'Windows PowerShell 5.1 ou superior e necessario.' }
  if(-not [Environment]::Is64BitOperatingSystem) { throw 'Esta versao do SR Studio requer Windows 64 bits.' }

  Write-Setup 'Validando arquivos do instalador...'
  $bootstrapSource = Test-PackageFile 'SRStudioBootstrap.ps1' '__BOOTSTRAP_SHA__' __BOOTSTRAP_SIZE__
  $launcherSource = Test-PackageFile 'SRStudioLauncher.ps1' '__LAUNCHER_SHA__' __LAUNCHER_SIZE__
  $graphics2UpdaterSource = Test-PackageFile 'SRGraphics2Component.ps1' '__GRAPHICS2_UPDATER_SHA__' __GRAPHICS2_UPDATER_SIZE__
  $iconSource = Test-PackageFile 'SR_Studio.ico' '__ICON_SHA__' __ICON_SIZE__

  foreach($dirPath in @($SrRoot,$AppDir,$DataDir,$CacheDir,$ConfigDir,$LauncherDir,$RuntimeDir,$LogDir,$BackupDir,$StagingDir,$UninstallDir)) {
    New-Item -ItemType Directory -Path $dirPath -Force | Out-Null
  }
  Write-Setup ('Instalador ' + $InstallerVersion + ' iniciado.')

  Write-Setup 'Instalando Launcher local...'
  Copy-Item -LiteralPath $bootstrapSource -Destination (Join-Path $LauncherDir 'SRStudioBootstrap.ps1') -Force
  Copy-Item -LiteralPath $launcherSource -Destination (Join-Path $LauncherDir 'SRStudioLauncher.ps1') -Force
  Copy-Item -LiteralPath $graphics2UpdaterSource -Destination (Join-Path $LauncherDir 'SRGraphics2Component.ps1') -Force
  Copy-Item -LiteralPath $iconSource -Destination (Join-Path $LauncherDir 'SR_Studio.ico') -Force

  foreach($scriptName in @('SRStudioBootstrap.ps1','SRStudioLauncher.ps1','SRGraphics2Component.ps1')) {
    $tokens = $null; $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $LauncherDir $scriptName),[ref]$tokens,[ref]$parseErrors) | Out-Null
    if($parseErrors -and $parseErrors.Count -gt 0) { throw ($scriptName + ' invalido: ' + $parseErrors[0].Message) }
  }

  $configPath = Join-Path $ConfigDir 'launcher.json'
  $existingConfig = $null
  if(Test-Path $configPath) {
    try { $existingConfig = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json } catch { }
  }
  if($null -eq $existingConfig) {
    $config = [ordered]@{
      schema = 3
      channel = $Channel
      auto_update = $true
      repair_on_start = $true
      full_repair_every_days = 7
      allow_offline = $true
      remote_manifest_base = $OfficialRepositoryBase
      local_repository = ''
      entrypoint = 'SR_Studio_Gerador.py'
      python_command = ''
      encartes_cloud_url = 'http://127.0.0.1:3000'
      keep_backups = 3
      connect_timeout_seconds = 15
      download_timeout_seconds = 300
      download_retries = 3
      auto_update_launcher = $true
    }
  } else {
    $config = $existingConfig
    if(-not ($config.PSObject.Properties.Name -contains 'remote_manifest_base')) { $config | Add-Member -NotePropertyName remote_manifest_base -NotePropertyValue $OfficialRepositoryBase }
    else { $config.remote_manifest_base = $OfficialRepositoryBase }
    if(-not ($config.PSObject.Properties.Name -contains 'channel')) { $config | Add-Member -NotePropertyName channel -NotePropertyValue $Channel }
    else { $config.channel = $Channel }
    if(-not ($config.PSObject.Properties.Name -contains 'entrypoint')) { $config | Add-Member -NotePropertyName entrypoint -NotePropertyValue 'SR_Studio_Gerador.py' }
    if(-not ($config.PSObject.Properties.Name -contains 'python_command')) { $config | Add-Member -NotePropertyName python_command -NotePropertyValue '' }
    else {
      $pc=[string]$config.python_command
      if($pc -and (($pc -match '\\WindowsApps\\') -or -not (Test-Path -LiteralPath ([Environment]::ExpandEnvironmentVariables($pc)) -PathType Leaf))) { $config.python_command = '' }
    }
  }
  Save-SetupJson $config $configPath
  Write-Setup ('Configuracao salva. Canal atual: ' + [string]$config.channel)

  $openCmd = Join-Path $SrRoot 'ABRIR_SR_STUDIO.cmd'
  $repairCmd = Join-Path $SrRoot 'REPARAR_SR_STUDIO.cmd'
  $diagnoseCmd = Join-Path $SrRoot 'DIAGNOSTICAR_SR_STUDIO.cmd'
  $uninstallCmd = Join-Path $SrRoot 'DESINSTALAR_SR_STUDIO.cmd'
  Write-CmdFile $openCmd @('@echo off','"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SRStudio\Launcher\SRStudioBootstrap.ps1"')
  Write-CmdFile $repairCmd @('@echo off','"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SRStudio\Launcher\SRStudioBootstrap.ps1" -RepairOnly -FullRepair','pause')
  Write-CmdFile $diagnoseCmd @('@echo off','"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SRStudio\Launcher\Diagnosticar.ps1"','pause')
  Write-CmdFile $uninstallCmd @('@echo off','"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\SRStudio\Uninstall\Desinstalar.ps1"')

  $diagnostic = @'
$ErrorActionPreference = 'Continue'
$root = Join-Path $env:LOCALAPPDATA 'SRStudio'
Write-Host '=== SR STUDIO - DIAGNOSTICO ==='
Write-Host ('Pasta: ' + $root)
$config = Join-Path $root 'Config\launcher.json'
$installed = Join-Path $root 'Config\installed.json'
$integrity = Join-Path $root 'Config\integrity.json'
$g2Receipt = Join-Path $root 'App\Graphics2Host\graphics2-host-install.json'
if(Test-Path $config) { Write-Host ''; Write-Host 'CONFIGURACAO:'; Get-Content -Raw $config }
if(Test-Path $installed) { Write-Host ''; Write-Host 'VERSAO INSTALADA:'; Get-Content -Raw $installed }
if(Test-Path $integrity) { try { $i=Get-Content -Raw $integrity|ConvertFrom-Json; Write-Host ''; Write-Host ('CATALOGO DE INTEGRIDADE: ' + @($i.files).Count + ' arquivos') } catch {} }
if(Test-Path $g2Receipt) { Write-Host ''; Write-Host 'GRAPHICS ENGINE 2 HOST:'; Get-Content -Raw $g2Receipt }
$log = Join-Path $root 'Logs\launcher.log'
if(Test-Path $log) { Write-Host ''; Write-Host 'ULTIMAS LINHAS DO LOG:'; Get-Content $log -Tail 25 }
'@
  [IO.File]::WriteAllText((Join-Path $LauncherDir 'Diagnosticar.ps1'),$diagnostic,(New-Object Text.UTF8Encoding($true)))

  $uninstaller = @'
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:LOCALAPPDATA 'SRStudio'
try { Add-Type -AssemblyName PresentationFramework -ErrorAction Stop } catch { }
$result = [System.Windows.MessageBox]::Show('Deseja remover o SR Studio deste computador?\n\nSIM = remover programa e manter a pasta Data.\nNAO = cancelar.','Desinstalar SR Studio','YesNo','Question')
if($result -ne 'Yes') { return }
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
Remove-Item -LiteralPath (Join-Path $desktop 'SR Studio.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $desktop 'Reparar SR Studio.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $programs 'SR Studio') -Recurse -Force -ErrorAction SilentlyContinue
foreach($name in @('App','Cache','Config','Launcher','Runtime','Logs','Backups','Staging')) {
  $p = Join-Path $root $name
  if(Test-Path $p) { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue }
}
Get-ChildItem -LiteralPath $root -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
[System.Windows.MessageBox]::Show('SR Studio removido. A pasta Data foi preservada em:\n' + (Join-Path $root 'Data'),'SR Studio') | Out-Null
'@
  [IO.File]::WriteAllText((Join-Path $UninstallDir 'Desinstalar.ps1'),$uninstaller,(New-Object Text.UTF8Encoding($true)))

  Write-Setup 'Criando atalhos...'
  $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
  $bootstrap = Join-Path $LauncherDir 'SRStudioBootstrap.ps1'
  $desktop = [Environment]::GetFolderPath('Desktop')
  $programs = [Environment]::GetFolderPath('Programs')
  $menuDir = Join-Path $programs 'SR Studio'
  New-Item -ItemType Directory -Path $menuDir -Force | Out-Null
  $openArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $bootstrap + '"'
  $repairArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + $bootstrap + '" -RepairOnly -FullRepair'
  $diagArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $LauncherDir 'Diagnosticar.ps1') + '"'
  $uninstallArgs = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $UninstallDir 'Desinstalar.ps1') + '"'
  New-SrShortcut (Join-Path $desktop 'SR Studio.lnk') $openArgs 'Abrir SR Studio'
  New-SrShortcut (Join-Path $menuDir 'SR Studio.lnk') $openArgs 'Abrir SR Studio'
  New-SrShortcut (Join-Path $menuDir 'Reparar SR Studio.lnk') $repairArgs 'Verificar e reparar SR Studio'
  New-SrShortcut (Join-Path $menuDir 'Diagnosticar SR Studio.lnk') $diagArgs 'Diagnostico do SR Studio'
  New-SrShortcut (Join-Path $menuDir 'Desinstalar SR Studio.lnk') $uninstallArgs 'Desinstalar SR Studio'

  Write-Setup 'Testando acesso ao repositorio Stable/Beta...'
  $manifestTest = Join-Path $CacheDir ('setup_' + $Channel + '_manifest.json')
  Invoke-WebRequest -UseBasicParsing -Uri ($OfficialRepositoryBase + '/' + $Channel + '/manifest.json') -OutFile $manifestTest -TimeoutSec 30 -Headers @{'Cache-Control'='no-cache'}
  $manifest = Get-Content -Raw -LiteralPath $manifestTest | ConvertFrom-Json
  if([string]$manifest.format -ne 'SRSTUDIO_HYBRID_BUNDLE_1') { throw 'O repositorio online ainda nao esta pronto para instalacao por bundle.' }
  Write-Setup ('Repositorio OK. Versao disponivel: ' + [string]$manifest.version)

  Write-Host ''
  Write-Host 'Agora o instalador vai baixar o Desktop Core e preparar o runtime privado.'
  Write-Host 'Na primeira instalacao isso pode demorar alguns minutos.'
  Write-Host ''
  $powershellExe = Join-Path $PSHOME 'powershell.exe'
  $bootstrapPath = Join-Path $LauncherDir 'SRStudioBootstrap.ps1'
  $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$bootstrapPath)
  if($NoLaunch) { $args += '-NoLaunch' }
  & $powershellExe @args
  $childExit = $LASTEXITCODE
  if($childExit -ne 0) { throw ('O Launcher retornou codigo ' + $childExit + '. Consulte ' + (Join-Path $LogDir 'launcher.log')) }

  if(-not (Test-Path (Join-Path $AppDir 'SR_Studio_Gerador.py'))) { throw 'O Desktop Core nao foi instalado corretamente.' }
  if(-not $NoLaunch -and -not (Test-Path (Join-Path $RuntimeDir 'python\python.exe'))) {
    throw 'O runtime privado do Python nao foi preparado corretamente.'
  }

  $setupState = [ordered]@{
    installer_version = $InstallerVersion
    installed_at = (Get-Date).ToString('o')
    channel = [string]$config.channel
    zero_admin = $true
    install_root = $SrRoot
    graphics2_component_updater = (Join-Path $LauncherDir 'SRGraphics2Component.ps1')
  }
  Save-SetupJson $setupState (Join-Path $ConfigDir 'setup.json')
  Write-Setup 'INSTALACAO CONCLUIDA COM SUCESSO.'
  Write-Host ''
  Write-Host '============================================================'
  Write-Host ' SR STUDIO ESTA PRONTO.'
  Write-Host ' Um atalho foi criado na Area de Trabalho.'
  Write-Host '============================================================'
  if($NoLaunch) { Write-Host 'Use o atalho SR Studio para abrir o programa.' }
}
catch {
  $message = $_.Exception.Message
  try { Write-Setup ('ERRO: ' + $message) } catch { Write-Host ('ERRO: ' + $message) }
  Show-SetupError ('Nao foi possivel concluir a instalacao do SR Studio.' + [Environment]::NewLine + [Environment]::NewLine + $message + [Environment]::NewLine + [Environment]::NewLine + 'Log: ' + $SetupLog)
  Write-Host ''
  Write-Host ('ERRO: ' + $message)
  Write-Host ('Log: ' + $SetupLog)
  exit 1
}
