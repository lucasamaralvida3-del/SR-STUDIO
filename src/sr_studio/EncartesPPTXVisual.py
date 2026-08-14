from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

from EncartesAssets import safe_name


def _powershell_exe():
    candidates=[]
    system_root=os.environ.get('SystemRoot') or os.environ.get('WINDIR') or ''
    if system_root:
        candidates.append(str(Path(system_root)/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'))
    candidates.extend([shutil.which('powershell.exe'),shutil.which('powershell')])
    for item in candidates:
        if item and Path(item).is_file():
            return str(Path(item))
    return ''


def _script_text():
    return r'''param(
  [Parameter(Mandatory=$true)][string]$Pptx,
  [Parameter(Mandatory=$true)][string]$Spec,
  [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference = "Stop"

function Hide-DynamicShapes($shapes, $ids, $names) {
  for ($i = $shapes.Count; $i -ge 1; $i--) {
    $shape = $shapes.Item($i)
    try {
      $sid = [int]$shape.Id
      $sname = [string]$shape.Name
      if ($ids.ContainsKey($sid) -or $names.ContainsKey($sname)) {
        $shape.Visible = 0
      }
      if ([int]$shape.Type -eq 6) {
        Hide-DynamicShapes $shape.GroupItems $ids $names
      }
    } catch {}
  }
}

$ppt = $null
$presentation = $null
try {
  $items = Get-Content -Raw -LiteralPath $Spec | ConvertFrom-Json
  $ppt = New-Object -ComObject PowerPoint.Application
  try { $ppt.DisplayAlerts = 1 } catch {}
  try { $ppt.AutomationSecurity = 3 } catch {}
  $presentation = $ppt.Presentations.Open($Pptx, $true, $false, $false)

  foreach ($item in @($items)) {
    $slide = $presentation.Slides.Item([int]$item.slide)
    $ids = @{}
    foreach ($id in @($item.hide_ids)) {
      try { $ids[[int]$id] = $true } catch {}
    }
    $names = @{}
    foreach ($name in @($item.hide_names)) {
      if ($null -ne $name -and [string]$name -ne '') { $names[[string]$name] = $true }
    }
    Hide-DynamicShapes $slide.Shapes $ids $names
    $outPath = Join-Path $OutDir ([string]$item.file)
    $slide.Export($outPath, 'PNG', [int]$item.width, [int]$item.height)
  }
} finally {
  if ($null -ne $presentation) { try { $presentation.Close() } catch {} }
  if ($null -ne $ppt) { try { $ppt.Quit() } catch {} }
}
'''


def render_slide_backgrounds(data:bytes,pages:list[dict],asset_dir:Path,source_name='modelo.pptx'):
    """Renderiza o slide original pelo PowerPoint e oculta apenas campos dinâmicos.

    Em sistemas sem PowerPoint/PowerShell, retorna fallback estrutural sem impedir a importação.
    """
    if os.name!='nt':
        return {'mode':'xml-fallback','warning':'Renderização visual completa requer Windows com Microsoft PowerPoint instalado.','urls':[]}
    ps=_powershell_exe()
    if not ps:
        return {'mode':'xml-fallback','warning':'PowerShell não encontrado; usando importação estrutural do PPTX.','urls':[]}

    pptx_name=safe_name(source_name,'modelo.pptx')
    if Path(pptx_name).suffix.lower()!='.pptx': pptx_name=Path(pptx_name).stem+'.pptx'
    pptx_path=asset_dir/pptx_name
    pptx_path.write_bytes(data)

    spec=[]
    for index,page in enumerate(pages,1):
        render_w=1600
        render_h=max(400,round(render_w*(float(page.get('height') or 1123)/float(page.get('width') or 794))))
        spec.append({
            'slide':index,
            'file':f'slide_{index:03d}_design.png',
            'width':render_w,
            'height':render_h,
            'hide_ids':[int(x) for x in page.get('_dynamicPptxIds',[]) if str(x).isdigit()],
            'hide_names':[str(x) for x in page.get('_dynamicPptxNames',[]) if str(x).strip()],
        })

    spec_path=asset_dir/'render_spec.json'
    script_path=asset_dir/'render_pptx.ps1'
    spec_path.write_text(json.dumps(spec,ensure_ascii=False),encoding='utf-8')
    script_path.write_text(_script_text(),encoding='utf-8')

    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    try:
        proc=subprocess.run(
            [ps,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script_path),'-Pptx',str(pptx_path),'-Spec',str(spec_path),'-OutDir',str(asset_dir)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=max(90,min(300,45+25*len(spec))),creationflags=flags
        )
        if proc.returncode!=0:
            detail=(proc.stderr or proc.stdout or '').strip().splitlines()
            msg=detail[-1][:240] if detail else 'PowerPoint não conseguiu renderizar o arquivo.'
            return {'mode':'xml-fallback','warning':'Design completo não renderizado: '+msg,'urls':[]}
    except subprocess.TimeoutExpired:
        return {'mode':'xml-fallback','warning':'O PowerPoint demorou demais para renderizar o PPTX; usando modo estrutural.','urls':[]}
    except Exception as exc:
        return {'mode':'xml-fallback','warning':'Falha ao renderizar design completo: '+str(exc),'urls':[]}

    urls=[]
    for item in spec:
        p=asset_dir/item['file']
        if not p.is_file() or p.stat().st_size<1024:
            return {'mode':'xml-fallback','warning':'O PowerPoint não gerou todas as páginas do design; usando modo estrutural.','urls':[]}
        urls.append('/api/encartes/pptx-asset?session='+quote(asset_dir.name)+'&name='+quote(item['file']))
    return {'mode':'powerpoint-render','warning':'','urls':urls}
