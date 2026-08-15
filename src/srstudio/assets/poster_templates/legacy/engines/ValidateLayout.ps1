param(
    [Parameter(Mandatory=$true)][string]$JobsJson,
    [Parameter(Mandatory=$true)][string]$OutputJson,
    [Parameter(Mandatory=$true)][string]$Model1,
    [Parameter(Mandatory=$true)][string]$Model2,
    [Parameter(Mandatory=$true)][string]$Model1Limit,
    [Parameter(Mandatory=$true)][string]$Model2Limit,
    [Parameter(Mandatory=$true)][string]$ClubModel,
    [Parameter(Mandatory=$true)][string]$ClubModelLimit
)
$ErrorActionPreference = "Stop"

function Get-ShapeByName($slide, [string]$name) {
    for ($i = 1; $i -le $slide.Shapes.Count; $i++) {
        $sh = $slide.Shapes.Item($i)
        if ($sh.Name -eq $name) { return $sh }
    }
    throw "Campo '$name' não encontrado no modelo."
}

function Set-ShapeTextSafe($shape, [string]$text) {
    $ok = $false

    try {
        $shape.TextFrame2.TextRange.Text = $text
        $ok = $true
    } catch {}

    if (-not $ok) {
        try {
            $shape.TextFrame.TextRange.Text = $text
            $ok = $true
        } catch {}
    }

    if (-not $ok) {
        throw ("Não foi possível alterar o texto do campo '" + $shape.Name + "'.")
    }
}

function Set-FontNameSafe($shape, [string]$fontName) {
    try {
        $shape.TextFrame2.TextRange.Font.Name = $fontName
        return
    } catch {}
    try {
        $shape.TextFrame.TextRange.Font.Name = $fontName
    } catch {}
}

function Set-FontSizeSafe($shape, [double]$fontSize) {
    try {
        $shape.TextFrame2.TextRange.Font.Size = $fontSize
        return $true
    } catch {}
    try {
        $shape.TextFrame.TextRange.Font.Size = $fontSize
        return $true
    } catch {}
    return $false
}

function Get-TextBoundsSafe($shape) {
    try {
        return @(
            [double]$shape.TextFrame2.TextRange.BoundWidth,
            [double]$shape.TextFrame2.TextRange.BoundHeight
        )
    } catch {}
    return $null
}

function Set-TextExact($shape, [string]$text, [double]$fontSize) {
    try { $shape.TextFrame2.AutoSize = 0 } catch {}
    try { $shape.TextFrame.AutoSize = 0 } catch {}

    Set-ShapeTextSafe $shape $text
    Set-FontNameSafe $shape "Algerian"
    [void](Set-FontSizeSafe $shape $fontSize)
}

function Set-TextPreserveStyle($shape, [string]$text) {
    try { $shape.TextFrame2.AutoSize = 0 } catch {}
    try { $shape.TextFrame.AutoSize = 0 } catch {}
    Set-ShapeTextSafe $shape $text
}

function Set-FitText($shape, [string]$text, [double]$originalSize, [double]$minSize, [double]$widthPct, [double]$heightPct) {
    try { $shape.TextFrame2.AutoSize = 0 } catch {}
    try { $shape.TextFrame.AutoSize = 0 } catch {}
    try { $shape.TextFrame2.WordWrap = -1 } catch {}
    try { $shape.TextFrame.WordWrap = -1 } catch {}

    Set-ShapeTextSafe $shape $text.ToUpperInvariant()
    Set-FontNameSafe $shape "Algerian"

    $size = $originalSize
    $canResize = Set-FontSizeSafe $shape $size

    # Alguns PowerPoints/Office retornam ArgumentException em BoundWidth/Font.Size
    # para certos WordArts. Nesses casos mantemos o estilo do modelo e seguimos.
    if (-not $canResize) { return }

    for ($i = 0; $i -lt 100; $i++) {
        $bounds = Get-TextBoundsSafe $shape
        if ($null -eq $bounds) { break }

        $fits = $true
        try {
            if (($bounds[0] -gt ([double]$shape.Width * $widthPct)) -or
                ($bounds[1] -gt ([double]$shape.Height * $heightPct))) {
                $fits = $false
            }
        } catch {
            break
        }

        if ($fits -or $size -le $minSize) { break }

        $size -= 1.0
        if (-not (Set-FontSizeSafe $shape $size)) { break }
    }
}

function Set-ProductFit($shape, [string]$text, [double]$originalSize, [double]$minSize) {
    Set-FitText $shape $text $originalSize $minSize 0.96 0.94
}

function Set-CampaignFit($shape, [string]$text, [double]$originalSize, [double]$minSize) {
    Set-FitText $shape $text $originalSize $minSize 0.97 0.95
}

function Format-Validity([string]$label, [string]$period) {
    if ([string]::IsNullOrWhiteSpace($period)) { return $label }
    return ($label + "`r" + $period)
}
function Format-Limit([string]$value) {
    if ([string]::IsNullOrWhiteSpace($value)) { return "" }
    $v = $value.Trim()
    if ($v.ToUpperInvariant().StartsWith("LIMITE")) { return $v.ToUpperInvariant() }
    return ("LIMITE DE " + $v.ToUpperInvariant() + " POR CPF")
}
function Safe-FileName([string]$s) {
    $bad = [System.IO.Path]::GetInvalidFileNameChars()
    foreach ($c in $bad) { $s = $s.Replace([string]$c, "_") }
    if ($s.Length -gt 65) { $s = $s.Substring(0,65) }
    return $s
}
function Select-Model($job, $Model1, $Model2, $Model1Limit, $Model2Limit, $ClubModel, $ClubModelLimit) {
    $hasLimit = -not [string]::IsNullOrWhiteSpace([string]$job.limite)
    if ([int]$job.tipo -eq 1) {
        if ($hasLimit) { return $Model1Limit } else { return $Model1 }
    } elseif ([int]$job.tipo -eq 2) {
        if ($hasLimit) { return $Model2Limit } else { return $Model2 }
    } else {
        if ($hasLimit) { return $ClubModelLimit } else { return $ClubModel }
    }
}
function Apply-JobToSlide($slide, $job) {
    $hasLimit = -not [string]::IsNullOrWhiteSpace([string]$job.limite)
    $validText = Format-Validity ([string]$job.validade_rotulo) ([string]$job.validade)

    if ([int]$job.tipo -eq 1) {
        $campaign = Get-ShapeByName $slide "SR_CAMPANHA"
        $prod = Get-ShapeByName $slide "SR_PRODUTO"
        $promo = Get-ShapeByName $slide "SR_PRECO_PROMO"
        $valid = Get-ShapeByName $slide "SR_VALIDADE"
        $unit = Get-ShapeByName $slide "SR_UNIDADE"
        Set-ProductFit $prod ([string]$job.produto) 54.0 20.0
        Set-TextExact $promo ([string]$job.promocao) 45.92
        Set-TextExact $valid $validText 48.0
        Set-TextExact $unit ([string]$job.unidade_exibicao) 14.0
        Set-CampaignFit $campaign ([string]$job.campanha) 48.0 15.0
        if ($hasLimit) {
            $limit = Get-ShapeByName $slide "SR_LIMITE"
            Set-TextPreserveStyle $limit (Format-Limit ([string]$job.limite))
        }
    } elseif ([int]$job.tipo -eq 2) {
        $campaign = Get-ShapeByName $slide "SR_CAMPANHA"
        $prod = Get-ShapeByName $slide "SR_PRODUTO"
        $promo = Get-ShapeByName $slide "SR_PRECO_PROMO"
        $clube = Get-ShapeByName $slide "SR_PRECO_CLUBE"
        $valid = Get-ShapeByName $slide "SR_VALIDADE"
        $unit1 = Get-ShapeByName $slide "SR_UNIDADE_PROMO"
        $unit2 = Get-ShapeByName $slide "SR_UNIDADE_CLUBE"
        Set-ProductFit $prod ([string]$job.produto) 40.0 18.0
        Set-TextExact $promo ([string]$job.promocao) 36.16
        Set-TextExact $clube ([string]$job.clube) 36.16
        Set-TextExact $valid $validText 40.0
        Set-TextExact $unit1 ([string]$job.unidade_exibicao) 12.0
        Set-TextExact $unit2 ([string]$job.unidade_exibicao) 12.0
        Set-CampaignFit $campaign ([string]$job.campanha) 40.0 12.0
        if ($hasLimit) {
            $limit = Get-ShapeByName $slide "SR_LIMITE"
            Set-TextPreserveStyle $limit (Format-Limit ([string]$job.limite))
        }
    } else {
        $prod = Get-ShapeByName $slide "SR_CLUBE_PRODUTO"
        $price = Get-ShapeByName $slide "SR_CLUBE_PRECO"
        $valid = Get-ShapeByName $slide "SR_CLUBE_VALIDADE"
        Set-ProductFit $prod ([string]$job.produto) 40.0 18.0
        Set-TextPreserveStyle $price ([string]$job.clube)
        Set-TextPreserveStyle $valid $validText
        if ($hasLimit) {
            $limit = Get-ShapeByName $slide "SR_CLUBE_LIMITE"
            Set-TextPreserveStyle $limit (Format-Limit ([string]$job.limite))
        }
    }
}
function Test-TextOverflow($shape, [double]$wPct=1.02, [double]$hPct=1.02) {
    try {
        $tr = $shape.TextFrame2.TextRange
        if (($tr.BoundWidth -gt ($shape.Width * $wPct)) -or
            ($tr.BoundHeight -gt ($shape.Height * $hPct))) { return $true }
    } catch {}
    return $false
}

$ppt=$null
$results=@()
try {
    $jobs=Get-Content -LiteralPath $JobsJson -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($jobs -isnot [System.Array]) { $jobs=@($jobs) }
    $pptType=[type]::GetTypeFromProgID("PowerPoint.Application")
    if ($null -eq $pptType) { throw "Microsoft PowerPoint não está registrado no Windows." }
    $ppt=[Activator]::CreateInstance($pptType)
    $ppt.Visible=-1
    $idx=0
    foreach ($job in $jobs) {
        $idx++
        $pres=$null; $slide=$null
        try {
            $model=Select-Model $job $Model1 $Model2 $Model1Limit $Model2Limit $ClubModel $ClubModelLimit
            $pres=$ppt.Presentations.Open($model,0,0,0)
            $slide=$pres.Slides.Item(1)
            Apply-JobToSlide $slide $job

            $prod = if ([int]$job.tipo -eq 3) { Get-ShapeByName $slide "SR_CLUBE_PRODUTO" } else { Get-ShapeByName $slide "SR_PRODUTO" }
            $details=@()
            if (Test-TextOverflow $prod) { $details += "Descrição ultrapassa a área do produto." }
            if ([int]$job.tipo -ne 3) {
                $campaign=Get-ShapeByName $slide "SR_CAMPANHA"
                if (Test-TextOverflow $campaign) { $details += "Enunciado ultrapassa a área da campanha." }
            }
            $prodFont=0
            try { $prodFont=[double]$prod.TextFrame2.TextRange.Font.Size } catch {}
            if (([int]$job.tipo -eq 1 -and $prodFont -le 22) -or ([int]$job.tipo -eq 2 -and $prodFont -le 20)) {
                $details += "Fonte do produto foi reduzida bastante."
            }

            # Confere campos principais, inclusive limite quando houver.
            if ([int]$job.tipo -eq 3) {
                $names=@("SR_CLUBE_VALIDADE","SR_CLUBE_PRECO")
                if (-not [string]::IsNullOrWhiteSpace([string]$job.limite)) { $names += "SR_CLUBE_LIMITE" }
            } else {
                $names=@("SR_VALIDADE","SR_PRECO_PROMO")
                if ([int]$job.tipo -eq 2) { $names += "SR_PRECO_CLUBE" }
                if (-not [string]::IsNullOrWhiteSpace([string]$job.limite)) { $names += "SR_LIMITE" }
            }
            foreach ($nm in $names) {
                $sh=Get-ShapeByName $slide $nm
                if (Test-TextOverflow $sh) { $details += ("Campo " + $nm + " ultrapassa a área disponível.") }
            }
            $status=if ($details.Count -gt 0) { "REVISAR" } else { "OK" }
            $results += [PSCustomObject]@{
                job_id=[string]$job.id
                status=$status
                detail=($details -join " ")
                product_font=$prodFont
            }
            Write-Output ("CHECK|{0}|{1}|{2}" -f $idx,$status,[string]$job.produto)
        }
        catch {
            $results += [PSCustomObject]@{
                job_id=[string]$job.id
                status="ERRO"
                detail=$_.Exception.Message
                product_font=0
            }
            Write-Output ("CHECK|{0}|ERRO|{1}" -f $idx,[string]$job.produto)
        }
        finally {
            if ($null -ne $pres) { try { $pres.Saved=-1; $pres.Close() } catch {} }
            foreach ($o in @($slide,$pres)) { if ($null -ne $o) { try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($o) } catch {} } }
            [GC]::Collect(); [GC]::WaitForPendingFinalizers()
        }
    }
    ConvertTo-Json -InputObject @($results) -Depth 5 | Set-Content -LiteralPath $OutputJson -Encoding UTF8
}
finally {
    if ($null -ne $ppt) { try { $ppt.Quit() } catch {}; try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($ppt) } catch {} }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
