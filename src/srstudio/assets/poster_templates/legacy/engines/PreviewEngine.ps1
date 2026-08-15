param(
    [Parameter(Mandatory=$true)][string]$JobJson,
    [Parameter(Mandatory=$true)][string]$OutputPng,
    [Parameter(Mandatory=$true)][string]$Model1,
    [Parameter(Mandatory=$true)][string]$Model2,
    [Parameter(Mandatory=$true)][string]$Model1Limit,
    [Parameter(Mandatory=$true)][string]$Model2Limit,
    [Parameter(Mandatory=$true)][string]$ClubModel,
    [Parameter(Mandatory=$true)][string]$ClubModelLimit,
    [Parameter(Mandatory=$true)][string]$SaleModel
)
$ErrorActionPreference = "Stop"

function Get-ShapeByName($slide, [string]$name) {
    for ($i = 1; $i -le $slide.Shapes.Count; $i++) {
        $sh = $slide.Shapes.Item($i)
        if ($sh.Name -eq $name) { return $sh }
    }
    throw "Campo '$name' não encontrado no modelo."
}


function Get-ShapeTextSafe($shape) {
    try { return [string]$shape.TextFrame2.TextRange.Text } catch {}
    try { return [string]$shape.TextFrame.TextRange.Text } catch {}
    return ""
}

function Get-ShapeByTextLike($slide, [string]$snippet) {
    $needle = ([string]$snippet).Trim().ToUpperInvariant()
    for ($i = 1; $i -le $slide.Shapes.Count; $i++) {
        $sh = $slide.Shapes.Item($i)
        $txt = (Get-ShapeTextSafe $sh).Trim().ToUpperInvariant()
        if ($txt -and $txt -eq $needle) { return $sh }
    }
    for ($i = 1; $i -le $slide.Shapes.Count; $i++) {
        $sh = $slide.Shapes.Item($i)
        $txt = (Get-ShapeTextSafe $sh).Trim().ToUpperInvariant()
        if ($txt -and $txt.Contains($needle)) { return $sh }
    }
    throw "Campo por texto '$snippet' não encontrado no modelo."
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

function Normalize-OneLineText([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) { return "" }
    return ((($text -replace "[\r\n]+", " ") -replace "\s+", " ").Trim().ToUpperInvariant())
}

function Get-BalancedTwoLineText([string]$text) {
    $base = Normalize-OneLineText $text
    if ([string]::IsNullOrWhiteSpace($base)) { return "" }
    $words = $base -split " "
    if ($words.Count -le 1) { return $base }

    $best = $base
    $bestScore = [double]::PositiveInfinity
    for ($i = 1; $i -lt $words.Count; $i++) {
        $left = ($words[0..($i-1)] -join " ").Trim()
        $right = ($words[$i..($words.Count-1)] -join " ").Trim()
        if ([string]::IsNullOrWhiteSpace($left) -or [string]::IsNullOrWhiteSpace($right)) { continue }

        $score = [math]::Abs($left.Length - $right.Length)
        if ($left.Length -gt 26) { $score += ($left.Length - 26) * 2.0 }
        if ($right.Length -gt 26) { $score += ($right.Length - 26) * 2.0 }
        if ($left.Length -lt 7 -or $right.Length -lt 7) { $score += 8.0 }

        $firstRightWord = ($right -split " ")[0]
        if ($firstRightWord -in @("KG","G","GR","L","ML","UN","UND","CX","FD","PCT")) { $score += 4.0 }
        if ($firstRightWord -in @("DE","DA","DO","DAS","DOS","COM","E")) { $score += 2.0 }

        if ($score -lt $bestScore) {
            $bestScore = $score
            $best = $left + "`r" + $right
        }
    }
    return $best
}

function Get-BalancedThreeLineText([string]$text) {
    $base = Normalize-OneLineText $text
    if ([string]::IsNullOrWhiteSpace($base)) { return "" }
    $words = $base -split " "
    if ($words.Count -le 2) { return $base }

    $best = $base
    $bestScore = [double]::PositiveInfinity
    for ($i = 1; $i -lt ($words.Count - 1); $i++) {
        for ($j = $i + 1; $j -lt $words.Count; $j++) {
            $l1 = ($words[0..($i-1)] -join " ").Trim()
            $l2 = ($words[$i..($j-1)] -join " ").Trim()
            $l3 = ($words[$j..($words.Count-1)] -join " ").Trim()
            if ([string]::IsNullOrWhiteSpace($l1) -or [string]::IsNullOrWhiteSpace($l2) -or [string]::IsNullOrWhiteSpace($l3)) { continue }

            $lens = @($l1.Length, $l2.Length, $l3.Length)
            $maxLen = ($lens | Measure-Object -Maximum).Maximum
            $minLen = ($lens | Measure-Object -Minimum).Minimum
            $score = ($maxLen - $minLen)
            foreach ($ln in @($l1,$l2,$l3)) {
                if ($ln.Length -gt 18) { $score += ($ln.Length - 18) * 2.0 }
                if ($ln.Length -lt 5) { $score += 8.0 }
                $firstWord = ($ln -split " ")[0]
                if ($firstWord -in @("KG","G","GR","L","ML","UN","UND","CX","FD","PCT")) { $score += 4.0 }
                if ($firstWord -in @("DE","DA","DO","DAS","DOS","COM","E")) { $score += 2.0 }
            }
            if ($score -lt $bestScore) {
                $bestScore = $score
                $best = $l1 + "`r" + $l2 + "`r" + $l3
            }
        }
    }
    return $best
}

function Find-FittedFontSize($shape, [double]$start, [double]$minSize, [double]$widthPct, [double]$heightPct) {
    $size = $start
    if (-not (Set-FontSizeSafe $shape $size)) { return $minSize }
    for ($i = 0; $i -lt 100; $i++) {
        if ((Test-CurrentFit $shape $widthPct $heightPct) -or $size -le $minSize) { break }
        $size -= 1.0
        if (-not (Set-FontSizeSafe $shape $size)) { break }
    }
    return $size
}

function Set-ProductFitKeepStyleMaxLines($shape, [string]$text, [double]$originalSize, [double]$minSize, [int]$maxLines) {
    try { $shape.TextFrame2.AutoSize = 0 } catch {}
    try { $shape.TextFrame.AutoSize = 0 } catch {}
    try { $shape.TextFrame2.WordWrap = -1 } catch {}
    try { $shape.TextFrame.WordWrap = -1 } catch {}

    $singleLine = Normalize-OneLineText $text
    $candidates = New-Object System.Collections.ArrayList
    [void]$candidates.Add($singleLine)
    if ($maxLines -ge 2) {
        $twoLines = Get-BalancedTwoLineText $singleLine
        if (-not [string]::IsNullOrWhiteSpace($twoLines) -and $twoLines -ne $singleLine) { [void]$candidates.Add($twoLines) }
    }
    if ($maxLines -ge 3) {
        $threeLines = Get-BalancedThreeLineText $singleLine
        if (-not [string]::IsNullOrWhiteSpace($threeLines) -and $threeLines -ne $singleLine) { [void]$candidates.Add($threeLines) }
    }

    $bestText = $singleLine
    $bestSize = $minSize
    $bestLines = 99
    foreach ($candidate in $candidates) {
        $lineCount = (($candidate -split "`r") | Measure-Object).Count
        Set-ShapeTextSafe $shape $candidate
        $size = Find-FittedFontSize $shape $originalSize $minSize 0.96 0.94
        if (($size -gt $bestSize) -or (($size -eq $bestSize) -and ($lineCount -lt $bestLines))) {
            $bestSize = $size
            $bestText = $candidate
            $bestLines = $lineCount
        }
    }
    Set-ShapeTextSafe $shape $bestText
    [void](Set-FontSizeSafe $shape $bestSize)
}

function Test-CurrentFit($shape, [double]$widthPct, [double]$heightPct) {
    $bounds = Get-TextBoundsSafe $shape
    if ($null -eq $bounds) { return $true }
    try {
        return (($bounds[0] -le ([double]$shape.Width * $widthPct)) -and
                ($bounds[1] -le ([double]$shape.Height * $heightPct)))
    } catch {
        return $true
    }
}

function Shrink-CurrentTextToFit($shape, [double]$start, [double]$minSize, [double]$widthPct, [double]$heightPct) {
    $size = $start
    if (-not (Set-FontSizeSafe $shape $size)) { return }
    for ($i = 0; $i -lt 100; $i++) {
        if ((Test-CurrentFit $shape $widthPct $heightPct) -or $size -le $minSize) { break }
        $size -= 1.0
        if (-not (Set-FontSizeSafe $shape $size)) { break }
    }
}

function Set-FitTextKeepStyle($shape, [string]$text, [double]$originalSize, [double]$minSize, [double]$widthPct, [double]$heightPct) {
    try { $shape.TextFrame2.AutoSize = 0 } catch {}
    try { $shape.TextFrame.AutoSize = 0 } catch {}
    try { $shape.TextFrame2.WordWrap = -1 } catch {}
    try { $shape.TextFrame.WordWrap = -1 } catch {}

    Set-ShapeTextSafe $shape $text
    $canResize = Set-FontSizeSafe $shape $originalSize
    if (-not $canResize) { return }
    Shrink-CurrentTextToFit $shape $originalSize $minSize $widthPct $heightPct
}

function Set-ProductFitKeepStyle($shape, [string]$text, [double]$originalSize, [double]$minSize) {
    try { $shape.TextFrame2.AutoSize = 0 } catch {}
    try { $shape.TextFrame.AutoSize = 0 } catch {}
    try { $shape.TextFrame2.WordWrap = -1 } catch {}
    try { $shape.TextFrame.WordWrap = -1 } catch {}

    $singleLine = Normalize-OneLineText $text
    Set-ShapeTextSafe $shape $singleLine
    [void](Set-FontSizeSafe $shape $originalSize)
    if (Test-CurrentFit $shape 0.96 0.94) { return }

    $twoLines = Get-BalancedTwoLineText $singleLine
    if ([string]::IsNullOrWhiteSpace($twoLines)) { $twoLines = $singleLine }
    Set-ShapeTextSafe $shape $twoLines
    Shrink-CurrentTextToFit $shape $originalSize $minSize 0.96 0.94
}

function Set-ProductFit($shape, [string]$text, [double]$originalSize, [double]$minSize) {
    try { $shape.TextFrame2.AutoSize = 0 } catch {}
    try { $shape.TextFrame.AutoSize = 0 } catch {}
    try { $shape.TextFrame2.WordWrap = -1 } catch {}
    try { $shape.TextFrame.WordWrap = -1 } catch {}

    $singleLine = Normalize-OneLineText $text
    Set-ShapeTextSafe $shape $singleLine
    Set-FontNameSafe $shape "Algerian"
    [void](Set-FontSizeSafe $shape $originalSize)

    # Primeiro tenta manter em uma linha. Se não couber, passa para duas linhas.
    if (Test-CurrentFit $shape 0.96 0.94) { return }

    $twoLines = Get-BalancedTwoLineText $singleLine
    if ([string]::IsNullOrWhiteSpace($twoLines)) { $twoLines = $singleLine }

    Set-ShapeTextSafe $shape $twoLines
    Set-FontNameSafe $shape "Algerian"
    Shrink-CurrentTextToFit $shape $originalSize $minSize 0.96 0.94
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
function Select-Model($job, $Model1, $Model2, $Model1Limit, $Model2Limit, $ClubModel, $ClubModelLimit, $SaleModel) {
    $hasLimit = -not [string]::IsNullOrWhiteSpace([string]$job.limite)
    if ([int]$job.tipo -eq 1) {
        if ($hasLimit) { return $Model1Limit } else { return $Model1 }
    } elseif ([int]$job.tipo -eq 2) {
        if ($hasLimit) { return $Model2Limit } else { return $Model2 }
    } elseif ([int]$job.tipo -eq 3) {
        if ($hasLimit) { return $ClubModelLimit } else { return $ClubModel }
    } else {
        return $SaleModel
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
    } elseif ([int]$job.tipo -eq 3) {
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
    } else {
        $prod = Get-ShapeByName $slide "SR_VENDA_PRODUTO"
        $price = Get-ShapeByName $slide "SR_VENDA_PRECO"
        $unit = Get-ShapeByName $slide "SR_VENDA_UNIDADE"
        Set-ProductFitKeepStyleMaxLines $prod ([string]$job.produto) 66.0 24.0 3
        Set-TextPreserveStyle $price ([string]$job.promocao)
        Set-TextPreserveStyle $unit ([string]$job.unidade_exibicao)
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

$ppt=$null; $pres=$null; $slide=$null
try {
    $job = Get-Content -LiteralPath $JobJson -Raw -Encoding UTF8 | ConvertFrom-Json
    $pptType=[type]::GetTypeFromProgID("PowerPoint.Application")
    if ($null -eq $pptType) { throw "Microsoft PowerPoint não está registrado no Windows." }
    $ppt=[Activator]::CreateInstance($pptType)
    $ppt.Visible=-1
    $model = Select-Model $job $Model1 $Model2 $Model1Limit $Model2Limit $ClubModel $ClubModelLimit $SaleModel
    $pres=$ppt.Presentations.Open($model,0,0,0)
    $slide=$pres.Slides.Item(1)
    Apply-JobToSlide $slide $job
    $slide.Export($OutputPng, "PNG", 900, 1250)
    if (-not (Test-Path -LiteralPath $OutputPng)) { throw "A prévia PNG não foi criada." }
}
finally {
    if ($null -ne $pres) { try { $pres.Saved=-1; $pres.Close() } catch {} }
    if ($null -ne $ppt) { try { $ppt.Quit() } catch {} }
    foreach ($o in @($slide,$pres,$ppt)) { if ($null -ne $o) { try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($o) } catch {} } }
    [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}
