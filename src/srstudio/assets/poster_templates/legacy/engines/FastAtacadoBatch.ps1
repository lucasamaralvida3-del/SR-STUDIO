param(
    [Parameter(Mandatory=$true)][string]$JobsJson,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [Parameter(Mandatory=$true)][string]$BaseEngine,
    [Parameter(Mandatory=$true)][string]$Model,
    [int]$Width = 1772,
    [int]$Height = 2480
)
$ErrorActionPreference = "Stop"

# Same strategy as FastPromotionBatch.ps1: preserve the proven AtacadoEngine
# and only add persistent cache destinations for PDF + PNG in the same pass.
$source = Get-Content -LiteralPath $BaseEngine -Raw -Encoding UTF8

$pdfNeedle = '$pdf=Join-Path $OutputDir ("{0:D3}_{1}.pdf" -f $idx,$safe)'
if (-not $source.Contains($pdfNeedle)) {
    throw "AtacadoEngine oficial mudou: ponto de PDF não encontrado."
}
$pdfReplacement = @'
            if ($null -ne $job.PSObject.Properties["output_pdf"] -and -not [string]::IsNullOrWhiteSpace([string]$job.output_pdf)) {
                $pdf=[string]$job.output_pdf
                $pdfParent=Split-Path -Parent $pdf
                if($pdfParent){New-Item -ItemType Directory -Force -Path $pdfParent | Out-Null}
            } else {
                $pdf=Join-Path $OutputDir ("{0:D3}_{1}.pdf" -f $idx,$safe)
            }
'@
$source = $source.Replace($pdfNeedle, $pdfReplacement.TrimEnd())

$manifestNeedle = '            $files+=$pdf'
if (-not $source.Contains($manifestNeedle)) {
    throw "AtacadoEngine oficial mudou: ponto de manifesto não encontrado."
}
$previewInjection = @'
            if($null -ne $job.PSObject.Properties["output_png"] -and -not [string]::IsNullOrWhiteSpace([string]$job.output_png)){
                $png=[string]$job.output_png
                $pngParent=Split-Path -Parent $png
                if($pngParent){New-Item -ItemType Directory -Force -Path $pngParent | Out-Null}
                if(Test-Path -LiteralPath $png){Remove-Item -LiteralPath $png -Force -ErrorAction SilentlyContinue}
                $slide.Export($png,"PNG",__SR_WIDTH__,__SR_HEIGHT__)
                if(-not (Test-Path -LiteralPath $png)){throw "O PowerPoint não criou a prévia PNG: $png"}
            }
            $files+=$pdf
'@
$previewInjection = $previewInjection.Replace('__SR_WIDTH__',[string]$Width).Replace('__SR_HEIGHT__',[string]$Height)
$source = $source.Replace($manifestNeedle, $previewInjection.TrimEnd())

$visibleNeedle = '$ppt.Visible=-1'
if ($source.Contains($visibleNeedle)) {
    $visibleReplacement = @'
$ppt.Visible=-1
try{
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SRStudioBatchWindowWholesale {
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@ -ErrorAction SilentlyContinue
    [void][SRStudioBatchWindowWholesale]::ShowWindow([IntPtr]$ppt.HWND,0)
}catch{}
'@
    $source = $source.Replace($visibleNeedle, $visibleReplacement.TrimEnd())
}

$tempScript = Join-Path ([System.IO.Path]::GetTempPath()) ("srstudio-fast-atacado-" + [guid]::NewGuid().ToString("N") + ".ps1")
try {
    Set-Content -LiteralPath $tempScript -Value $source -Encoding UTF8
    & $tempScript -JobsJson $JobsJson -OutputDir $OutputDir -Model $Model
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
}
