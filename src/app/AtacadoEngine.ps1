param(
    [Parameter(Mandatory=$true)][string]$JobsJson,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [Parameter(Mandatory=$true)][string]$Model
)
$ErrorActionPreference="Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SRStudioWin32 {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@

function Get-ShapeByName($slide,[string]$name){
    for($i=1;$i -le $slide.Shapes.Count;$i++){
        $s=$slide.Shapes.Item($i)
        if($s.Name -eq $name){ return $s }
    }
    throw "Campo '$name' não encontrado no modelo Atacado."
}
function Set-TextSafe($shape,[string]$text){
    $ok=$false
    try{$shape.TextFrame2.TextRange.Text=$text;$ok=$true}catch{}
    if(-not $ok){try{$shape.TextFrame.TextRange.Text=$text;$ok=$true}catch{}}
    if(-not $ok){throw "Não foi possível alterar o campo '$($shape.Name)'."}
}
function Set-SizeSafe($shape,[double]$size){
    try{$shape.TextFrame2.TextRange.Font.Size=$size;return $true}catch{}
    try{$shape.TextFrame.TextRange.Font.Size=$size;return $true}catch{}
    return $false
}
function Bounds($shape){
    try{return @([double]$shape.TextFrame2.TextRange.BoundWidth,[double]$shape.TextFrame2.TextRange.BoundHeight)}catch{}
    return $null
}
function Set-Preserve($shape,[string]$text){
    try{$shape.TextFrame2.AutoSize=0}catch{}
    try{$shape.TextFrame.AutoSize=0}catch{}
    Set-TextSafe $shape $text
}
function Set-Fit($shape,[string]$text,[double]$start,[double]$min){
    try{$shape.TextFrame2.AutoSize=0}catch{}
    try{$shape.TextFrame.AutoSize=0}catch{}
    try{$shape.TextFrame2.WordWrap=-1}catch{}
    try{$shape.TextFrame.WordWrap=-1}catch{}
    Set-TextSafe $shape $text
    $size=$start
    if(-not (Set-SizeSafe $shape $size)){return}
    for($i=0;$i -lt 80;$i++){
        $b=Bounds $shape
        if($null -eq $b){break}
        $fits=$true
        try{
            if(($b[0] -gt ([double]$shape.Width*0.96)) -or ($b[1] -gt ([double]$shape.Height*0.94))){$fits=$false}
        }catch{break}
        if($fits -or $size -le $min){break}
        $size-=1
        if(-not (Set-SizeSafe $shape $size)){break}
    }
}
function Normalize-OneLineText([string]$text){
    if([string]::IsNullOrWhiteSpace($text)){return ""}
    return (((($text -replace "[\r\n]+"," ") -replace "\s+"," ")).Trim().ToUpperInvariant())
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
    $b=Bounds $shape
    if($null -eq $b){return $true}
    try{return (($b[0] -le ([double]$shape.Width*$wPct)) -and ($b[1] -le ([double]$shape.Height*$hPct)))}catch{return $true}
}
function Shrink-CurrentTextToFit($shape,[double]$start,[double]$min,[double]$wPct,[double]$hPct){
    $size=$start
    if(-not (Set-SizeSafe $shape $size)){return}
    for($i=0;$i -lt 100;$i++){
        if((Test-CurrentFit $shape $wPct $hPct) -or $size -le $min){break}
        $size-=1
        if(-not (Set-SizeSafe $shape $size)){break}
    }
}
function Set-ProductNameFit($shape,[string]$text,[double]$start,[double]$min){
    try{$shape.TextFrame2.AutoSize=0}catch{}
    try{$shape.TextFrame.AutoSize=0}catch{}
    try{$shape.TextFrame2.WordWrap=-1}catch{}
    try{$shape.TextFrame.WordWrap=-1}catch{}
    $single=Normalize-OneLineText $text
    Set-TextSafe $shape $single
    [void](Set-SizeSafe $shape $start)
    if(Test-CurrentFit $shape 0.96 0.94){return}
    $two=Get-BalancedTwoLineText $single
    if([string]::IsNullOrWhiteSpace($two)){$two=$single}
    Set-TextSafe $shape $two
    Shrink-CurrentTextToFit $shape $start $min 0.96 0.94
}

function Safe-FileName([string]$s){
    foreach($c in [System.IO.Path]::GetInvalidFileNameChars()){$s=$s.Replace([string]$c,"_")}
    if($s.Length -gt 70){$s=$s.Substring(0,70)}
    return $s
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$jobs=Get-Content -LiteralPath $JobsJson -Raw -Encoding UTF8 | ConvertFrom-Json
$t=[type]::GetTypeFromProgID("PowerPoint.Application")
if($null -eq $t){throw "Microsoft PowerPoint não está registrado no Windows."}
$ppt=[Activator]::CreateInstance($t)
$ppt.Visible=-1
try {
    [uint32]$srPptPid=0
    [void][SRStudioWin32]::GetWindowThreadProcessId([IntPtr]$ppt.HWND,[ref]$srPptPid)
    if($srPptPid -gt 0){ Write-Output ("PPTPID|{0}" -f $srPptPid) }
}catch{}
$files=@()
$errors=@()
$idx=0
try{
    foreach($job in $jobs){
        $idx++
        $pres=$null;$slide=$null
        try{
            Write-Output ("STAGE|{0}|ABRINDO_MODELO" -f $idx)
            $pres=$ppt.Presentations.Open($Model,0,0,0)
            $slide=$pres.Slides.Item(1)
            Write-Output ("STAGE|{0}|PREENCHENDO" -f $idx)

            $nome=Get-ShapeByName $slide "SR_ATACADO_NOME"
            $varejo=Get-ShapeByName $slide "SR_ATACADO_VAREJO"
            $preco=Get-ShapeByName $slide "SR_ATACADO_PRECO"
            $total=Get-ShapeByName $slide "SR_ATACADO_TOTAL"
            $qtd=Get-ShapeByName $slide "SR_ATACADO_QUANTIDADE"
            $qtd2=Get-ShapeByName $slide "SR_ATACADO_QUANTIDADE_2"

            Set-ProductNameFit $nome ([string]$job.nome) 43 18
            Set-Preserve $varejo ([string]$job.varejo)
            Set-Preserve $preco ([string]$job.atacado)
            Set-Preserve $total ("R$ " + [string]$job.total)
            Set-Fit $qtd ([string]$job.quantidade_texto).ToUpperInvariant() 22 12
            Set-Fit $qtd2 ([string]$job.quantidade_2_texto).ToUpperInvariant() 16 9

            $safe=Safe-FileName ([string]$job.nome)
            $pdf=Join-Path $OutputDir ("{0:D3}_{1}.pdf" -f $idx,$safe)
            Write-Output ("STAGE|{0}|SALVANDO_PDF" -f $idx)
            $pres.SaveAs($pdf,32,0)
            if(-not (Test-Path -LiteralPath $pdf)){throw "O PowerPoint não criou o PDF: $pdf"}
            $files+=$pdf
            Write-Output ("OK|{0}|{1}" -f $idx,$pdf)
        }catch{
            $msg=$_.Exception.Message
            $errors += [PSCustomObject]@{index=$idx;nome=[string]$job.nome;message=$msg}
            $clean=$msg.Replace("`r"," ").Replace("`n"," ")
            Write-Output ("ERR|{0}|{1}" -f $idx,$clean)
        }finally{
            # Evita bloqueio de FinalReleaseComObject/GC após o SaveAs.
            if($null -ne $pres){try{$pres.Saved=-1;$pres.Close()}catch{}}
            $slide=$null;$pres=$null
        }
    }
    $manifest=Join-Path $OutputDir "manifest.txt"
    $files | Set-Content -LiteralPath $manifest -Encoding UTF8
    $errorFile=Join-Path $OutputDir "errors.json"
    @($errors) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $errorFile -Encoding UTF8
    Write-Output ("BATCH_DONE|{0}" -f $files.Count)
}finally{
    if($null -ne $ppt){try{$ppt.Quit()}catch{}}
    $ppt=$null
    Write-Output "ENGINE_DONE"
}
