param(
  [Parameter(Mandatory=$true)][string]$InputDir,
  [Parameter(Mandatory=$true)][string]$Output,
  [ValidateSet('PDF','PPTX')][string]$Format='PDF',
  [int]$Width=1080,
  [int]$Height=1350
)
$ErrorActionPreference='Stop'
$images=Get-ChildItem -LiteralPath $InputDir -Filter '*.png' | Sort-Object Name
if(-not $images -or $images.Count -lt 1){throw 'Nenhuma pagina PNG foi recebida para exportacao.'}
if($Width -lt 10){$Width=1080};if($Height -lt 10){$Height=1350}
$ppt=$null;$pres=$null
try{
  $ppt=New-Object -ComObject PowerPoint.Application
  $ppt.Visible=-1
  $pres=$ppt.Presentations.Add()
  $base=720.0
  if($Width -ge $Height){$slideW=$base;$slideH=$base*([double]$Height/[double]$Width)}
  else{$slideW=$base;$slideH=$base*([double]$Height/[double]$Width)}
  $pres.PageSetup.SlideWidth=$slideW
  $pres.PageSetup.SlideHeight=$slideH
  foreach($img in $images){
    $slide=$pres.Slides.Add($pres.Slides.Count+1,12)
    $pic=$slide.Shapes.AddPicture($img.FullName,$false,$true,0,0,$pres.PageSetup.SlideWidth,$pres.PageSetup.SlideHeight)
    $pic.LockAspectRatio=0
  }
  if($Format -eq 'PDF'){$pres.ExportAsFixedFormat($Output,2)}else{$pres.SaveAs($Output,24)}
  if(-not (Test-Path -LiteralPath $Output)){throw 'O PowerPoint nao criou o arquivo final.'}
}
finally{
  if($pres){try{$pres.Close()}catch{};[void][Runtime.InteropServices.Marshal]::ReleaseComObject($pres)}
  if($ppt){try{$ppt.Quit()}catch{};[void][Runtime.InteropServices.Marshal]::ReleaseComObject($ppt)}
  [GC]::Collect();[GC]::WaitForPendingFinalizers()
}
