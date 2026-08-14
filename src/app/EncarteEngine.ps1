param(
    [Parameter(Mandatory=$true)][string]$JobsJson,
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateSet('PNG','PDF')][string]$OutputType='PNG',
    [string]$LogoPath=''
)
$ErrorActionPreference='Stop'

function RGB([int]$r,[int]$g,[int]$b){ return ($r + ($g * 256) + ($b * 65536)) }
function Add-Rect($slide,[double]$x,[double]$y,[double]$w,[double]$h,[int]$fill,[double]$radius=0){
    $type=1
    if($radius -gt 0){$type=5}
    $s=$slide.Shapes.AddShape($type,$x,$y,$w,$h)
    $s.Fill.ForeColor.RGB=$fill;$s.Fill.Solid();$s.Line.Visible=0
    return $s
}
function Add-Text($slide,[string]$text,[double]$x,[double]$y,[double]$w,[double]$h,[double]$size,[int]$color,[int]$bold=0,[int]$align=1){
    $s=$slide.Shapes.AddTextbox(1,$x,$y,$w,$h)
    $s.TextFrame2.TextRange.Text=$text
    $s.TextFrame2.MarginLeft=0;$s.TextFrame2.MarginRight=0;$s.TextFrame2.MarginTop=0;$s.TextFrame2.MarginBottom=0
    $s.TextFrame2.WordWrap=-1;$s.TextFrame2.AutoSize=0
    $s.TextFrame2.TextRange.Font.Name='Arial'
    $s.TextFrame2.TextRange.Font.Size=$size
    $s.TextFrame2.TextRange.Font.Bold=$bold
    $s.TextFrame2.TextRange.Font.Fill.ForeColor.RGB=$color
    $s.TextFrame2.TextRange.ParagraphFormat.Alignment=$align
    return $s
}
function Fit-Text($shape,[double]$start,[double]$min){
    $size=$start
    try{$shape.TextFrame2.TextRange.Font.Size=$size}catch{return}
    for($i=0;$i -lt 80;$i++){
        try{
            $b=$shape.TextFrame2.TextRange.BoundHeight
            if($b -le ($shape.Height*0.96) -or $size -le $min){break}
            $size-=1;$shape.TextFrame2.TextRange.Font.Size=$size
        }catch{break}
    }
}
function Add-ContainPicture($slide,[string]$path,[double]$x,[double]$y,[double]$w,[double]$h){
    if([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path)){return $null}
    try{
        $pic=$slide.Shapes.AddPicture($path,0,-1,$x,$y,-1,-1)
        $ratio=[math]::Min($w/[double]$pic.Width,$h/[double]$pic.Height)
        $pic.LockAspectRatio=-1;$pic.Width=$pic.Width*$ratio;$pic.Height=$pic.Height*$ratio
        $pic.Left=$x+($w-$pic.Width)/2;$pic.Top=$y+($h-$pic.Height)/2
        return $pic
    }catch{return $null}
}
function Add-ProductCard($slide,$item,[double]$x,[double]$y,[double]$w,[double]$h,[switch]$Hero){
    $blue=RGB 0 67 132;$dark=RGB 20 31 51;$muted=RGB 89 102 121;$green=RGB 23 117 72;$white=RGB 255 255 255;$line=RGB 224 230 238
    $card=Add-Rect $slide $x $y $w $h $white 8
    $card.Line.Visible=-1;$card.Line.ForeColor.RGB=$line;$card.Line.Weight=1
    $pad=[math]::Max(8,$w*0.035)
    $imgH=if($Hero){$h*0.48}else{$h*0.43}
    $pic=Add-ContainPicture $slide ([string]$item.imagem) ($x+$pad) ($y+$pad) ($w-2*$pad) ($imgH-$pad)
    if($null -eq $pic){
        $ph=Add-Rect $slide ($x+$pad) ($y+$pad) ($w-2*$pad) ($imgH-$pad) (RGB 246 248 251) 5
        $t=Add-Text $slide 'SEM IMAGEM' ($x+$pad) ($y+$imgH*0.42) ($w-2*$pad) 20 10 $muted 1 2
    }
    $nameY=$y+$imgH+4
    $nameH=if($Hero){$h*0.19}else{$h*0.21}
    $nameSize=15;$nameMin=9;$unitSize=9;$priceTop=50;$priceH=43;$rsSize=9;$rsY=5;$priceFont=21;$priceTextH=38
    if($Hero){$nameSize=23;$nameMin=14;$unitSize=12;$priceTop=70;$priceH=57;$rsSize=12;$rsY=10;$priceFont=29;$priceTextH=51}
    $name=Add-Text $slide ([string]$item.produto).ToUpperInvariant() ($x+$pad) $nameY ($w-2*$pad) $nameH $nameSize $dark 1 1
    Fit-Text $name $nameSize $nameMin
    $unit=[string]$item.unidade
    $price=[string]$item.preco
    $priceY=$y+$h-$priceTop
    $unitText=Add-Text $slide $unit ($x+$pad) ($priceY-2) ([math]::Min(65,$w*0.24)) 22 $unitSize $muted 1 1
    $priceBox=Add-Rect $slide ($x+$w*0.34) ($priceY-8) ($w*0.62-$pad) $priceH $blue 8
    $rs=Add-Text $slide 'R$' ($x+$w*0.365) ($priceY+$rsY) 28 22 $rsSize $white 1 1
    $pt=Add-Text $slide $price ($x+$w*0.43) ($priceY-3) ($w*0.49) $priceTextH $priceFont $white 1 2
    if($h -gt 200 -and -not [string]::IsNullOrWhiteSpace([string]$item.clube)){
        $tag=Add-Rect $slide ($x+$pad) ($y+$h-27) ($w*0.31) 19 $green 5
        Add-Text $slide ('CLUBE R$ '+[string]$item.clube) ($x+$pad+4) ($y+$h-24) ($w*0.31-8) 14 8 $white 1 2 | Out-Null
    }
}

$data=Get-Content -LiteralPath $JobsJson -Raw -Encoding UTF8 | ConvertFrom-Json
$ppt=$null;$pres=$null
try{
    $ppt=New-Object -ComObject PowerPoint.Application
    $ppt.Visible=-1
    $pres=$ppt.Presentations.Add()
    $pres.PageSetup.SlideWidth=720
    $pres.PageSetup.SlideHeight=900
    $slide=$pres.Slides.Add(1,12)
    # limpar placeholders eventuais
    for($i=$slide.Shapes.Count;$i -ge 1;$i--){try{$slide.Shapes.Item($i).Delete()}catch{}}

    $blue=RGB 0 67 132;$blue2=RGB 4 92 170;$dark=RGB 20 31 51;$white=RGB 255 255 255;$bg=RGB 244 247 251;$muted=RGB 104 117 137
    Add-Rect $slide 0 0 720 900 $bg | Out-Null
    Add-Rect $slide 0 0 720 126 $blue | Out-Null
    if($LogoPath -and (Test-Path -LiteralPath $LogoPath)){
        Add-ContainPicture $slide $LogoPath 25 17 110 70 | Out-Null
    }
    $title=Add-Text $slide ([string]$data.campanha).ToUpperInvariant() 155 24 535 58 30 $white 1 1
    Fit-Text $title 30 17
    if(-not [string]::IsNullOrWhiteSpace([string]$data.validade)){
        Add-Text $slide ('VÁLIDO: '+[string]$data.validade) 156 84 520 22 11 $white 1 1 | Out-Null
    }
    Add-Text $slide 'SUPERMERCADO RODRIGUES' 28 866 400 18 9 $muted 1 1 | Out-Null
    Add-Text $slide 'Ofertas sujeitas à disponibilidade de estoque.' 415 866 278 18 8 $muted 0 3 | Out-Null

    $items=@($data.items)
    $layout=[string]$data.layout
    if($layout -eq 'CAPA' -or $layout -eq 'DESTAQUE'){
        if($items.Count -gt 0){Add-ProductCard $slide $items[0] 95 165 530 650 -Hero}
    } elseif($layout -eq 'GRADE 4'){
        $positions=@(@(34,155),@(374,155),@(34,505),@(374,505))
        for($i=0;$i -lt [math]::Min(4,$items.Count);$i++){Add-ProductCard $slide $items[$i] $positions[$i][0] $positions[$i][1] 312 325}
    } elseif($layout -eq 'GRADE 6'){
        $positions=@(@(25,151),@(260,151),@(495,151),@(25,503),@(260,503),@(495,503))
        for($i=0;$i -lt [math]::Min(6,$items.Count);$i++){Add-ProductCard $slide $items[$i] $positions[$i][0] $positions[$i][1] 205 320}
    } elseif($layout -eq 'MISTO'){
        if($items.Count -gt 0){Add-ProductCard $slide $items[0] 28 151 322 672 -Hero}
        $positions=@(@(370,151),@(370,324),@(370,497),@(370,670))
        for($i=1;$i -lt [math]::Min(5,$items.Count);$i++){Add-ProductCard $slide $items[$i] 370 $positions[$i-1][1] 322 153}
    } else {
        if($items.Count -gt 0){Add-ProductCard $slide $items[0] 95 165 530 650 -Hero}
    }

    $out=[IO.Path]::GetFullPath($Output)
    if($OutputType -eq 'PDF'){
        $pres.SaveAs($out,32,0)
    }else{
        $slide.Export($out,'PNG',1080,1350)
    }
    Write-Output ('ENCARTE_DONE|'+$out)
}
finally{
    if($pres){try{$pres.Close()}catch{}}
    if($ppt){try{$ppt.Quit()}catch{}}
}
