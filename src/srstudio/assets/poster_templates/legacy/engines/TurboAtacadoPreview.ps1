param(
    [Parameter(Mandatory=$true)][string]$JobsJson,
    [Parameter(Mandatory=$true)][string]$BasePreviewEngine,
    [Parameter(Mandatory=$true)][string]$Model,
    [int]$Width = 1772,
    [int]$Height = 2480
)
$ErrorActionPreference = "Stop"

# Turbo Seguro para Atacado: UMA instância do PowerPoint por lote, com o modelo
# aberto/fechado para cada cartaz. Mantém o ganho principal de desempenho sem
# depender de Slides.Duplicate(), que varia entre versões/instalações do Office.
$source = Get-Content -LiteralPath $BasePreviewEngine -Raw -Encoding UTF8
$start = $source.IndexOf("function Get-ShapeByName")
$end = $source.IndexOf('$job=Get-Content')
if ($start -lt 0 -or $end -le $start) {
    throw "Não foi possível carregar as funções do AtacadoPreview oficial."
}
Invoke-Expression $source.Substring($start, $end - $start)

$jobs = @(Get-Content -LiteralPath $JobsJson -Raw -Encoding UTF8 | ConvertFrom-Json)
$t = [type]::GetTypeFromProgID("PowerPoint.Application")
if ($null -eq $t) { throw "Microsoft PowerPoint não está registrado no Windows." }
$ppt = [Activator]::CreateInstance($t)
try { $ppt.Visible = 0 } catch {}

try {
    $idx = 0
    foreach ($job in $jobs) {
        $idx++
        $pres = $null
        $slide = $null
        try {
            Write-Output ("START|{0}" -f $idx)
            $pres = $ppt.Presentations.Open($Model, 0, 0, 0)
            $slide = $pres.Slides.Item(1)
            Set-ProductNameFit (Get-ShapeByName $slide "SR_ATACADO_NOME") ([string]$job.nome) 43 18
            Set-T (Get-ShapeByName $slide "SR_ATACADO_VAREJO") ([string]$job.varejo)
            Set-T (Get-ShapeByName $slide "SR_ATACADO_PRECO") ([string]$job.atacado)
            Set-T (Get-ShapeByName $slide "SR_ATACADO_TOTAL") ("R$ " + [string]$job.total)
            Set-Fit (Get-ShapeByName $slide "SR_ATACADO_QUANTIDADE") ([string]$job.quantidade_texto).ToUpperInvariant() 22 12
            Set-Fit (Get-ShapeByName $slide "SR_ATACADO_QUANTIDADE_2") ([string]$job.quantidade_2_texto).ToUpperInvariant() 16 9

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
            if ($null -ne $pres) {
                try { $pres.Saved = -1; $pres.Close() } catch {}
            }
            $slide = $null
            $pres = $null
        }
    }
    Write-Output ("BATCH_DONE|{0}" -f $jobs.Count)
}
finally {
    if ($null -ne $ppt) { try { $ppt.Quit() } catch {} }
    $ppt = $null
    Write-Output "ENGINE_DONE"
}
