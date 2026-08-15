param(
    [Parameter(Mandatory=$true)][string]$JobJson,
    [Parameter(Mandatory=$true)][string]$OutputPng,
    [Parameter(Mandatory=$true)][string]$Model
)
$ErrorActionPreference="Stop"
function Get-ShapeByName($slide,[string]$name){
    for($i=1;$i -le $slide.Shapes.Count;$i++){$s=$slide.Shapes.Item($i);if($s.Name -eq $name){return $s}}
    throw "Campo '$name' não encontrado."
}
function Set-T($shape,[string]$text){
    $ok=$false
    try{$shape.TextFrame2.TextRange.Text=$text;$ok=$true}catch{}
    if(-not $ok){try{$shape.TextFrame.TextRange.Text=$text;$ok=$true}catch{}}
    if(-not $ok){throw "Não foi possível alterar '$($shape.Name)'."}
}
function Set-Size($shape,[double]$size){
    try{$shape.TextFrame2.TextRange.Font.Size=$size;return $true}catch{}
    try{$shape.TextFrame.TextRange.Font.Size=$size;return $true}catch{}
    return $false
}
function Get-Bounds($shape){
    try{return @([double]$shape.TextFrame2.TextRange.BoundWidth,[double]$shape.TextFrame2.TextRange.BoundHeight)}catch{}
    return $null
}
function Set-Fit($shape,[string]$text,[double]$start,[double]$min){
    try{$shape.TextFrame2.AutoSize=0}catch{}
    try{$shape.TextFrame.AutoSize=0}catch{}
    try{$shape.TextFrame2.WordWrap=-1}catch{}
    try{$shape.TextFrame.WordWrap=-1}catch{}
    Set-T $shape $text
    $size=$start
    if(-not (Set-Size $shape $size)){return}
    for($i=0;$i -lt 80;$i++){
        $b=Get-Bounds $shape
        if($null -eq $b){break}
        if(($b[0] -le ([double]$shape.Width*0.96)) -and ($b[1] -le ([double]$shape.Height*0.94))){break}
        if($size -le $min){break}
        $size-=1
        if(-not (Set-Size $shape $size)){break}
    }
}
function Normalize-OneLineText([string]$text){
    if([string]::IsNullOrWhiteSpace($text)){return ""}
    return (((($text -replace "[
]+"," ") -replace "\s+"," ")).Trim().ToUpperInvariant())
}
function Get-BalancedTwoLineText([string]$text){
    $base=Normalize-OneLineText $text
    if([string]::IsNullOrWhiteSpace($base)){return ""}
    $words=$base -split " "
    if($words.Count -le 1){return $base}
    $best=$base;$bestScore=[double]::PositiveInfinity
    for($i=1;$i -lt $words.Count;$i++){
        $left=(($words[0..($i-1)]) -join " ").Trim()
        $right=(($words[$i..($words.Count-1)]) -join " ").Trim()
        if([string]::IsNullOrWhiteSpace($left) -or [string]::IsNullOrWhiteSpace($right)){continue}
        $score=[math]::Abs($left.Length-$right.Length)
        if($left.Length -gt 26){$score+=($left.Length-26)*2.0}
        if($right.Length -gt 26){$score+=($right.Length-26)*2.0}
        if($left.Length -lt 7 -or $right.Length -lt 7){$score+=8.0}
        $firstRightWord=($right -split " ")[0]
        if($firstRightWord -in @("KG","G","GR","L","ML","UN","UND","CX","FD","PCT")){$score+=4.0}
        if($firstRightWord -in @("DE","DA","DO","DAS","DOS","COM","E")){$score+=2.0}
        if($score -lt $bestScore){$bestScore=$score;$best=$left+"`r"+$right}
    }
    return $best
}
function Test-CurrentFit($shape,[double]$wPct,[double]$hPct){
    $b=Get-Bounds $shape
    if($null -eq $b){return $true}
    try{return (($b[0] -le ([double]$shape.Width*$wPct)) -and ($b[1] -le ([double]$shape.Height*$hPct)))}catch{return $true}
}
function Shrink-CurrentTextToFit($shape,[double]$start,[double]$min,[double]$wPct,[double]$hPct){
    $size=$start
    if(-not (Set-Size $shape $size)){return}
    for($i=0;$i -lt 100;$i++){
        if((Test-CurrentFit $shape $wPct $hPct) -or $size -le $min){break}
        $size-=1
        if(-not (Set-Size $shape $size)){break}
    }
}
function Set-ProductNameFit($shape,[string]$text,[double]$start,[double]$min){
    try{$shape.TextFrame2.AutoSize=0}catch{}
    try{$shape.TextFrame.AutoSize=0}catch{}
    try{$shape.TextFrame2.WordWrap=-1}catch{}
    try{$shape.TextFrame.WordWrap=-1}catch{}
    $single=Normalize-OneLineText $text
    Set-T $shape $single
    [void](Set-Size $shape $start)
    if(Test-CurrentFit $shape 0.96 0.94){return}
    $two=Get-BalancedTwoLineText $single
    if([string]::IsNullOrWhiteSpace($two)){$two=$single}
    Set-T $shape $two
    Shrink-CurrentTextToFit $shape $start $min 0.96 0.94
}
$job=Get-Content -LiteralPath $JobJson -Raw -Encoding UTF8 | ConvertFrom-Json
$t=[type]::GetTypeFromProgID("PowerPoint.Application")
if($null -eq $t){throw "PowerPoint não registrado."}
$ppt=[Activator]::CreateInstance($t);$ppt.Visible=-1;$pres=$null
try{
    $pres=$ppt.Presentations.Open($Model,0,0,0);$s=$pres.Slides.Item(1)
    Set-ProductNameFit (Get-ShapeByName $s "SR_ATACADO_NOME") ([string]$job.nome) 43 18
    Set-T (Get-ShapeByName $s "SR_ATACADO_VAREJO") ([string]$job.varejo)
    Set-T (Get-ShapeByName $s "SR_ATACADO_PRECO") ([string]$job.atacado)
    Set-T (Get-ShapeByName $s "SR_ATACADO_TOTAL") ("R$ " + [string]$job.total)
    Set-Fit (Get-ShapeByName $s "SR_ATACADO_QUANTIDADE") ([string]$job.quantidade_texto).ToUpperInvariant() 22 12
    Set-Fit (Get-ShapeByName $s "SR_ATACADO_QUANTIDADE_2") ([string]$job.quantidade_2_texto).ToUpperInvariant() 16 9
    $s.Export($OutputPng,"PNG",900,1260)
    if(-not (Test-Path $OutputPng)){throw "A prévia não foi criada."}
}finally{
    if($null -ne $pres){try{$pres.Saved=-1;$pres.Close()}catch{}}
    if($null -ne $ppt){try{$ppt.Quit()}catch{}}
}
