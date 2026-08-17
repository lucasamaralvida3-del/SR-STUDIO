param(
  [switch]$RepairOnly,
  [switch]$NoLaunch,
  [switch]$FullRepair
)

$ErrorActionPreference = 'Stop'

$SrHomeRoot = Join-Path $env:LOCALAPPDATA 'SRStudio'
$CfgPath = Join-Path $SrHomeRoot 'Config\launcher.json'
$CorePath = Join-Path $PSScriptRoot 'SRStudioLauncherCore.ps1'

if(-not (Test-Path -LiteralPath $CorePath -PathType Leaf)) {
  throw 'SRStudioLauncherCore.ps1 is missing. Reopen the SR Studio Launcher to repair itself.'
}

$originalCfgText = $null
$cfgChanged = $false
$previousBeta = [Environment]::GetEnvironmentVariable('SR_GRAPHICS_ENGINE_2_BETA','Process')
$previousGpu = [Environment]::GetEnvironmentVariable('SR_GRAPHICS_ENGINE_2_GPU','Process')

try {
  $channel = 'stable'
  if(Test-Path -LiteralPath $CfgPath -PathType Leaf) {
    try {
      $originalCfgText = [IO.File]::ReadAllText($CfgPath)
      $cfg = $originalCfgText | ConvertFrom-Json
      if($cfg.PSObject.Properties.Name -contains 'channel') {
        $channel = [string]$cfg.channel
      }
      if($channel -eq 'beta') {
        if($cfg.PSObject.Properties.Name -contains 'entrypoint') {
          $cfg.entrypoint = 'SRStudio5/SR Studio 5.exe'
        } else {
          $cfg | Add-Member -NotePropertyName entrypoint -NotePropertyValue 'SRStudio5/SR Studio 5.exe'
        }
        $json = $cfg | ConvertTo-Json -Depth 30
        [IO.File]::WriteAllText($CfgPath,$json,(New-Object Text.UTF8Encoding($false)))
        $cfgChanged = $true

        [Environment]::SetEnvironmentVariable('SR_GRAPHICS_ENGINE_2_BETA','1','Process')
        [Environment]::SetEnvironmentVariable('SR_GRAPHICS_ENGINE_2_GPU','1','Process')
      }
    } catch {
      if($originalCfgText) {
        try { [IO.File]::WriteAllText($CfgPath,$originalCfgText,(New-Object Text.UTF8Encoding($false))) } catch { }
      }
      throw
    }
  }

  $coreArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$CorePath)
  if($RepairOnly) { $coreArgs += '-RepairOnly' }
  if($NoLaunch) { $coreArgs += '-NoLaunch' }
  if($FullRepair) { $coreArgs += '-FullRepair' }

  & powershell.exe @coreArgs
  $exitCode = $LASTEXITCODE
}
finally {
  if($cfgChanged -and $null -ne $originalCfgText) {
    try { [IO.File]::WriteAllText($CfgPath,$originalCfgText,(New-Object Text.UTF8Encoding($false))) } catch { }
  }
  [Environment]::SetEnvironmentVariable('SR_GRAPHICS_ENGINE_2_BETA',$previousBeta,'Process')
  [Environment]::SetEnvironmentVariable('SR_GRAPHICS_ENGINE_2_GPU',$previousGpu,'Process')
}

if($null -eq $exitCode) { $exitCode = 1 }
exit $exitCode
