param(
  [Parameter(Mandatory=$true)][string]$Model,
  [Parameter(Mandatory=$true)][string]$OutputPng
)
$ErrorActionPreference='Stop'
$ppt=$null;$pres=$null;$slide=$null
try{
  $t=[type]::GetTypeFromProgID('PowerPoint.Application')
  if($null -eq $t){throw 'Microsoft PowerPoint não está registrado no Windows.'}
  $ppt=[Activator]::CreateInstance($t);$ppt.Visible=-1
  $pres=$ppt.Presentations.Open($Model,0,0,0);$slide=$pres.Slides.Item(1)
  $slide.Export($OutputPng,'PNG',500,700)
  if(-not (Test-Path -LiteralPath $OutputPng)){throw 'Miniatura não foi criada.'}
}finally{
  if($null -ne $pres){try{$pres.Saved=-1;$pres.Close()}catch{}}
  if($null -ne $ppt){try{$ppt.Quit()}catch{}}
  foreach($o in @($slide,$pres,$ppt)){if($null -ne $o){try{[void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($o)}catch{}}}
  [GC]::Collect();[GC]::WaitForPendingFinalizers()
}
