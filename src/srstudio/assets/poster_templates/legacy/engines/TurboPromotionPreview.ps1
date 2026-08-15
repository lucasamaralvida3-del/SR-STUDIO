param(
    [Parameter(Mandatory=$true)][string]$JobsJson,
    [Parameter(Mandatory=$true)][string]$BasePreviewEngine,
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

# Reuse the exact historical fitting/model functions from PreviewEngine.ps1,
# but replace its one-job runtime with a persistent batch PowerPoint session.
$source = Get-Content -LiteralPath $BasePreviewEngine -Raw -Encoding UTF8
$start = $source.IndexOf("function Get-ShapeByName")
$end = $source.IndexOf('$ppt=$null; $pres=$null; $slide=$null')
if ($start -lt 0 -or $end -le $start) {
    throw "Não foi possível carregar as funções do PreviewEngine oficial."
}
Invoke-Expression $source.Substring($start, $end - $start)

$jobs = @(Get-Content -LiteralPath $JobsJson -Raw -Encoding UTF8 | ConvertFrom-Json)
$t = [type]::GetTypeFromProgID("PowerPoint.Application")
if ($null -eq $t) { throw "Microsoft PowerPoint não está registrado no Windows." }
$ppt = [Activator]::CreateInstance($t)
try { $ppt.Visible = 0 } catch {}
$presentations = @{}

function Get-OpenPresentation([string]$model) {
    if (-not $presentations.ContainsKey($model)) {
        $presentations[$model] = $ppt.Presentations.Open($model, 0, 0, 0)
    }
    return $presentations[$model]
}

try {
    $idx = 0
    foreach ($job in $jobs) {
        $idx++
        $slide = $null
        $range = $null
        try {
            Write-Output ("START|{0}" -f $idx)
            $model = Select-Model $job $Model1 $Model2 $Model1Limit $Model2Limit $ClubModel $ClubModelLimit $SaleModel
            $pres = Get-OpenPresentation $model
            $sourceSlide = $pres.Slides.Item(1)
            $range = $sourceSlide.Duplicate()
            $slide = $range.Item(1)
            Apply-JobToSlide $slide $job

            $output = [string]$job.output_png
            if ([string]::IsNullOrWhiteSpace($output)) { throw "Destino PNG ausente no job $idx." }
            $parent = Split-Path -Parent $output
            if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
            if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Force -ErrorAction SilentlyContinue }
            $slide.Export($output, "PNG", $Width, $Height)
            if (-not (Test-Path -LiteralPath $output)) { throw "PowerPoint não criou o PNG do job $idx." }
            Write-Output ("OK|{0}|{1}" -f $idx, $output)
        }
        catch {
            $clean = $_.Exception.Message.Replace("`r", " ").Replace("`n", " ")
            Write-Output ("ERR|{0}|{1}" -f $idx, $clean)
        }
        finally {
            if ($null -ne $slide) { try { $slide.Delete() } catch {} }
            $slide = $null
            $range = $null
        }
    }
    Write-Output ("BATCH_DONE|{0}" -f $jobs.Count)
}
finally {
    foreach ($key in @($presentations.Keys)) {
        $pres = $presentations[$key]
        if ($null -ne $pres) { try { $pres.Saved = -1; $pres.Close() } catch {} }
    }
    if ($null -ne $ppt) { try { $ppt.Quit() } catch {} }
    $presentations = @{}
    $ppt = $null
    Write-Output "ENGINE_DONE"
}
