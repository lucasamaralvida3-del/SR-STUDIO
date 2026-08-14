param(
  [Parameter(Mandatory=$true)][ValidateSet('Thumbnail','RemoveBackground')][string]$Mode,
  [Parameter(Mandatory=$true)][Alias('Input')][string]$InputPath,
  [Parameter(Mandatory=$true)][Alias('Output')][string]$OutputPath,
  [int]$Width = 420,
  [int]$Height = 420,
  [int]$Tolerance = 42
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing

if([string]::IsNullOrWhiteSpace($InputPath)){ throw 'O caminho da imagem de entrada não foi recebido.' }
if([string]::IsNullOrWhiteSpace($OutputPath)){ throw 'O caminho da imagem de saída não foi recebido.' }
try { $InputPath=[IO.Path]::GetFullPath([string]$InputPath) } catch {}
try {
  $parent=[IO.Path]::GetDirectoryName([string]$OutputPath)
  if($parent){ New-Item -ItemType Directory -Path $parent -Force | Out-Null }
} catch {}
if(-not (Test-Path -LiteralPath $InputPath -PathType Leaf)){ throw ('Imagem não encontrada: '+$InputPath) }

# IMPORTANTE: não usar uma variável chamada $Input aqui. $input é uma variável
# automática do PowerShell e fazia Bitmap.FromFile receber um objeto/valor inválido.
$src=[System.Drawing.Bitmap]::FromFile([string]$InputPath)
try {
  if($Mode -eq 'Thumbnail'){
    $ratio=[Math]::Min([double]$Width/$src.Width,[double]$Height/$src.Height)
    if($ratio -gt 1){$ratio=1}
    $w=[Math]::Max(1,[int]($src.Width*$ratio));$h=[Math]::Max(1,[int]($src.Height*$ratio))
    $bmp=New-Object System.Drawing.Bitmap($w,$h,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try{
      $g=[System.Drawing.Graphics]::FromImage($bmp)
      try{
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.InterpolationMode=[System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.PixelOffsetMode=[System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $g.SmoothingMode=[System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $g.DrawImage($src,0,0,$w,$h)
      } finally {$g.Dispose()}
      $bmp.Save([string]$OutputPath,[System.Drawing.Imaging.ImageFormat]::Png)
    } finally {$bmp.Dispose()}
  } else {
    $bmp=New-Object System.Drawing.Bitmap($src.Width,$src.Height,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try{
      $g=[System.Drawing.Graphics]::FromImage($bmp)
      try{$g.DrawImage($src,0,0,$src.Width,$src.Height)}finally{$g.Dispose()}
      $corners=@($bmp.GetPixel(0,0),$bmp.GetPixel($bmp.Width-1,0),$bmp.GetPixel(0,$bmp.Height-1),$bmp.GetPixel($bmp.Width-1,$bmp.Height-1))
      $r=[int](($corners|Measure-Object -Property R -Average).Average);$gg=[int](($corners|Measure-Object -Property G -Average).Average);$b=[int](($corners|Measure-Object -Property B -Average).Average)
      $tol=[Math]::Max(5,[Math]::Min(140,$Tolerance));$fade=[Math]::Max(8,[int]($tol*0.55))
      for($y=0;$y -lt $bmp.Height;$y++){
        for($x=0;$x -lt $bmp.Width;$x++){
          $c=$bmp.GetPixel($x,$y);$d=[Math]::Sqrt([Math]::Pow($c.R-$r,2)+[Math]::Pow($c.G-$gg,2)+[Math]::Pow($c.B-$b,2))
          if($d -le $tol){$a=0}
          elseif($d -le ($tol+$fade)){$a=[int](255*($d-$tol)/$fade)}
          else{$a=$c.A}
          $bmp.SetPixel($x,$y,[System.Drawing.Color]::FromArgb($a,$c.R,$c.G,$c.B))
        }
      }
      $bmp.Save([string]$OutputPath,[System.Drawing.Imaging.ImageFormat]::Png)
    } finally {$bmp.Dispose()}
  }
} finally {$src.Dispose()}
