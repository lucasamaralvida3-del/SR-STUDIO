from pathlib import Path
import json, hashlib

launcher = Path('launcher/files/SRStudioLauncher.ps1')
s = launcher.read_text(encoding='utf-8-sig')
s = s.replace("$LauncherVersion = '4.0.1-hybrid.base3.0'", "$LauncherVersion = '4.0.1-hybrid.base3.1'", 1)

marker = 'function Apply-SrBundleManifest($Source,$Manifest) {'
if 'function Repair-SrBundleManifest' not in s:
    repair = r'''function Repair-SrBundleManifest($Source,$Manifest) {
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

'''
    if marker not in s:
        raise SystemExit('Apply-SrBundleManifest marker not found')
    s = s.replace(marker, repair + marker, 1)

old = "function Apply-SrBundleManifest($Source,$Manifest) {\n  $targetVersion = [string]$Manifest.version"
new = "function Apply-SrBundleManifest($Source,$Manifest) {\n  $Manifest = Repair-SrBundleManifest $Source $Manifest\n  $targetVersion = [string]$Manifest.version"
if old not in s:
    raise SystemExit('Apply-SrBundleManifest insertion point not found')
s = s.replace(old, new, 1)

old_url = "$url = $baseUrl + '/' + $channel + '/manifest.json'"
new_url = "$url = $baseUrl + '/' + $channel + '/manifest.json?ts=' + [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"
if old_url in s:
    s = s.replace(old_url, new_url, 1)

old_prefix = "if(-not (Test-Path $sourceRoot)) { throw ('Bundle member prefix not found: ' + $memberPrefix) }"
new_prefix = """if(-not (Test-Path $sourceRoot)) {
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
    }"""
if old_prefix in s:
    s = s.replace(old_prefix, new_prefix, 1)

for token in ['4.0.1-hybrid.base3.1','Repair-SrBundleManifest','AUTO-REPAIR: manifesto bundle legado','last_manifest.repaired.json','manifest.json?ts=']:
    if token not in s:
        raise SystemExit('Missing token: ' + token)

launcher.write_text(s, encoding='utf-8')
raw = launcher.read_bytes()
manifest = {
    'format':'SRSTUDIO_LAUNCHER_MANIFEST_1',
    'product':'SR Studio Launcher',
    'version':'4.0.1-hybrid.base3.1',
    'published_at':'2026-08-14T15:55:00-03:00',
    'files':[{'path':'SRStudioLauncher.ps1','source':'launcher/files/SRStudioLauncher.ps1','sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}]
}
Path('manifests/launcher.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Launcher Base 3.1 AutoRepair ready', manifest['files'][0]['sha256'], len(raw))
