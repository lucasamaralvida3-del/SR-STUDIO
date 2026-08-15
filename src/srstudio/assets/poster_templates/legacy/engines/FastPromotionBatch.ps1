param(
    [Parameter(Mandatory=$true)][string]$JobsJson,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [Parameter(Mandatory=$true)][string]$BaseEngine,
    [Parameter(Mandatory=$true)][string]$Model1,
    [Parameter(Mandatory=$true)][string]$Model2,
    [Parameter(Mandatory=$true)][string]$Model1Limit,
    [Parameter(Mandatory=$true)][string]$Model2Limit,
    [Parameter(Mandatory=$true)][string]$ClubModel,
    [Parameter(Mandatory=$true)][string]$ClubModelLimit,
    [Parameter(Mandatory=$true)][string]$SaleModel,
    [int]$Width = 1772,
    [int]$Height = 2480
)
$ErrorActionPreference = "Stop"

# This wrapper does NOT reimplement the historical engine. It patches the proven
# PowerPointEngine.ps1 at runtime only to also emit the cached PNG/PDF paths that
# SR Studio 5 needs. All model selection, fitting and Office lifecycle remain the
# same as the Stable/Beta engine that already works on the user's machine.
$source = Get-Content -LiteralPath $BaseEngine -Raw -Encoding UTF8

$pdfNeedle = '$pdf = Join-Path $OutputDir ("{0:D3}_{1}_{2}.pdf" -f $idx, $safeCampaign, $safeProduct)'
if (-not $source.Contains($pdfNeedle)) {
    throw "PowerPointEngine oficial mudou: ponto de PDF não encontrado."
}
$pdfReplacement = @'
            if ($null -ne $job.PSObject.Properties["output_pdf"] -and -not [string]::IsNullOrWhiteSpace([string]$job.output_pdf)) {
                $pdf = [string]$job.output_pdf
                $pdfParent = Split-Path -Parent $pdf
                if ($pdfParent) { New-Item -ItemType Directory -Force -Path $pdfParent | Out-Null }
            } else {
                $pdf = Join-Path $OutputDir ("{0:D3}_{1}_{2}.pdf" -f $idx, $safeCampaign, $safeProduct)
            }
'@
$source = $source.Replace($pdfNeedle, $pdfReplacement.TrimEnd())

$manifestNeedle = '            $outFiles += $pdf'
if (-not $source.Contains($manifestNeedle)) {
    throw "PowerPointEngine oficial mudou: ponto de manifesto não encontrado."
}
$previewInjection = @'
            if ($null -ne $job.PSObject.Properties["output_png"] -and -not [string]::IsNullOrWhiteSpace([string]$job.output_png)) {
                $png = [string]$job.output_png
                $pngParent = Split-Path -Parent $png
                if ($pngParent) { New-Item -ItemType Directory -Force -Path $pngParent | Out-Null }
                if (Test-Path -LiteralPath $png) { Remove-Item -LiteralPath $png -Force -ErrorAction SilentlyContinue }
                $slide.Export($png, "PNG", __SR_WIDTH__, __SR_HEIGHT__)
                if (-not (Test-Path -LiteralPath $png)) { throw "O PowerPoint não criou a prévia PNG: $png" }
            }

            $outFiles += $pdf
'@
$previewInjection = $previewInjection.Replace('__SR_WIDTH__', [string]$Width).Replace('__SR_HEIGHT__', [string]$Height)
$source = $source.Replace($manifestNeedle, $previewInjection.TrimEnd())

# PowerPoint sometimes rejects Application.Visible = 0. Keep the proven Visible=-1
# behavior, then hide the actual HWND instead. If Windows refuses to hide it, the
# engine still continues exactly like the historical version instead of failing.
$visibleNeedle = '    $ppt.Visible = -1'
if ($source.Contains($visibleNeedle)) {
    $visibleReplacement = @'
    $ppt.Visible = -1
    try {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SRStudioBatchWindow {
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@ -ErrorAction SilentlyContinue
        [void][SRStudioBatchWindow]::ShowWindow([IntPtr]$ppt.HWND, 0)
    } catch {}
'@
    $source = $source.Replace($visibleNeedle, $visibleReplacement.TrimEnd())
}

$tempScript = Join-Path ([System.IO.Path]::GetTempPath()) ("srstudio-fast-promo-" + [guid]::NewGuid().ToString("N") + ".ps1")
try {
    Set-Content -LiteralPath $tempScript -Value $source -Encoding UTF8
    & $tempScript \
        -JobsJson $JobsJson \
        -OutputDir $OutputDir \
        -Model1 $Model1 \
        -Model2 $Model2 \
        -Model1Limit $Model1Limit \
        -Model2Limit $Model2Limit \
        -ClubModel $ClubModel \
        -ClubModelLimit $ClubModelLimit \
        -SaleModel $SaleModel
    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Remove-Item -LiteralPath $tempScript -Force -ErrorAction SilentlyContinue
}
