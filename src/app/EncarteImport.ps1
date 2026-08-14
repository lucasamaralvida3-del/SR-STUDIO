param(
  [Parameter(Mandatory=$true)][string]$InputPath,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [ValidateSet('ANALYZE','FAITHFUL','HYBRID','EDITABLE')][string]$Mode='EDITABLE'
)
$ErrorActionPreference='Stop'

function Fail([string]$Message) { throw $Message }
function HexFromRgb($rgb,[string]$fallback='#10213A') {
  try {
    $n=[int64]$rgb
    $r=$n -band 255; $g=($n -shr 8) -band 255; $b=($n -shr 16) -band 255
    return ('#{0:X2}{1:X2}{2:X2}' -f $r,$g,$b)
  } catch { return $fallback }
}
function Get-ShapeText($shape) {
  try {
    if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1){ return [string]$shape.TextFrame.TextRange.Text }
  } catch {}
  try {
    $t=[string]$shape.TextFrame2.TextRange.Text
    if(-not [string]::IsNullOrWhiteSpace($t)){ return $t }
  } catch {}
  return ''
}
function Get-TextRole([string]$txt) {
  $u=([string]$txt).Trim().ToUpperInvariant()
  if($u -match 'VÁLID|VALID|\d{1,2}/\d{1,2}/\d{2,4}') { return 'VALIDADE' }
  if($u -match '^(KG|UN|UND|CADA|À LATA|A LATA|À GARRAFA|A GARRAFA)$') { return 'UNIDADE' }
  if($u -match '^R\$\s*$' -or $u -match '^\d+[,.]\d{1,2}$') { return 'PRECO' }
  if($u -match 'TERÇA VERDE|TERCA VERDE|QUARTA CAF|QUINTA FIL|OFERTA|FIM DE SEMANA|CLUBE') { return 'TITULO' }
  return ''
}
function Export-ShapePng($shape,[string]$target) {
  try {
    # ppShapeFormatPNG = 2. O PowerPoint mantém transparência quando suportada.
    $shape.Export($target,2) | Out-Null
    if(Test-Path -LiteralPath $target){ return $true }
  } catch {}
  return $false
}
function ShapeBase($shape,[double]$sx,[double]$sy) {
  return [ordered]@{
    name=[string]$shape.Name
    x=[Math]::Round([double]$shape.Left*$sx,2)
    y=[Math]::Round([double]$shape.Top*$sy,2)
    w=[Math]::Round([Math]::Max(2,[double]$shape.Width*$sx),2)
    h=[Math]::Round([Math]::Max(2,[double]$shape.Height*$sy),2)
    z=[int]$shape.ZOrderPosition
    rotation=[Math]::Round([double]$shape.Rotation,2)
    opacity=1.0
  }
}
function Add-TextElement($elements,$shape,[string]$txt,[double]$sx,[double]$sy,[int]$zBoost=0) {
  if([string]::IsNullOrWhiteSpace($txt)){ return }
  $base=ShapeBase $shape $sx $sy
  $font='Segoe UI';$size=28;$color='#10213A';$bold=$false;$italic=$false;$align='left';$valign='top';$ml=0;$mr=0;$mt=0;$mb=0
  try{$font=[string]$shape.TextFrame2.TextRange.Font.Name}catch{try{$font=[string]$shape.TextFrame.TextRange.Font.Name}catch{}}
  try{$size=[double]$shape.TextFrame2.TextRange.Font.Size}catch{try{$size=[double]$shape.TextFrame.TextRange.Font.Size}catch{}}
  # PowerPoint mede fonte em pontos. O canvas do SR mede em pixels; aplicar a mesma escala usada na página.
  $size=[Math]::Max(6,[Math]::Round($size*$sy,1))
  try{$color=HexFromRgb $shape.TextFrame2.TextRange.Font.Fill.ForeColor.RGB '#10213A'}catch{try{$color=HexFromRgb $shape.TextFrame.TextRange.Font.Color.RGB '#10213A'}catch{}}
  try{$bold=([int]$shape.TextFrame2.TextRange.Font.Bold -ne 0)}catch{try{$bold=([int]$shape.TextFrame.TextRange.Font.Bold -ne 0)}catch{}}
  try{$italic=([int]$shape.TextFrame2.TextRange.Font.Italic -ne 0)}catch{try{$italic=([int]$shape.TextFrame.TextRange.Font.Italic -ne 0)}catch{}}
  try{
    $a=[int]$shape.TextFrame2.TextRange.ParagraphFormat.Alignment
    if($a -eq 2){$align='center'}elseif($a -eq 3){$align='right'}elseif($a -eq 4){$align='justify'}else{$align='left'}
  }catch{}
  try{
    $v=[int]$shape.TextFrame2.VerticalAnchor
    if($v -eq 3){$valign='middle'}elseif($v -eq 4){$valign='bottom'}else{$valign='top'}
  }catch{}
  try{$ml=[Math]::Round([double]$shape.TextFrame2.MarginLeft*$sx,1)}catch{}
  try{$mr=[Math]::Round([double]$shape.TextFrame2.MarginRight*$sx,1)}catch{}
  try{$mt=[Math]::Round([double]$shape.TextFrame2.MarginTop*$sy,1)}catch{}
  try{$mb=[Math]::Round([double]$shape.TextFrame2.MarginBottom*$sy,1)}catch{}
  $el=[ordered]@{
    type='text'; text=$txt; font=$font; size=$size; color=$color; bold=$bold; italic=$italic;
    align=$align; valign=$valign; margin_left=$ml; margin_right=$mr; margin_top=$mt; margin_bottom=$mb;
    role=(Get-TextRole $txt); fit=$true
  }
  foreach($k in $base.Keys){$el[$k]=$base[$k]}
  $el.z=[int]$base.z+$zBoost
  [void]$elements.Add($el)
}
function Flatten-Groups($slide) {
  # Desagrupa recursivamente somente msoGroup (6). Não desmonta fotos/OLE.
  # O PowerPoint atualiza a coleção Shapes depois de cada Ungroup, portanto percorremos de trás para frente e repetimos.
  $passes=0
  do {
    $changed=$false;$passes++
    for($i=[int]$slide.Shapes.Count;$i -ge 1;$i--){
      try {
        $sh=$slide.Shapes.Item($i)
        if([int]$sh.Type -eq 6){ $null=$sh.Ungroup(); $changed=$true }
      } catch {}
    }
  } while($changed -and $passes -lt 24)
  return $passes
}
function Get-ExportSize([double]$slideW,[double]$slideH) {
  $w=1080
  $ratio=$slideW/$slideH
  $target=1080.0/1350.0
  if([Math]::Abs($ratio-$target) -lt 0.03){$h=1350}else{$h=[Math]::Max(200,[int][Math]::Round($w/$ratio))}
  return @($w,$h)
}

if([string]::IsNullOrWhiteSpace($InputPath)){ Fail 'O caminho do arquivo para importação não foi recebido.' }
try { $InputPath=[IO.Path]::GetFullPath([string]$InputPath) } catch { $InputPath=[string]$InputPath }
if(-not (Test-Path -LiteralPath $InputPath -PathType Leaf)){ Fail ('Arquivo não encontrado: '+$InputPath) }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$ext=[IO.Path]::GetExtension([string]$InputPath); if($null -eq $ext){$ext=''}; $ext=$ext.Trim().ToLowerInvariant()
Write-Output ('INFO|EXT|'+$ext)

if($ext -in @('.png','.jpg','.jpeg','.bmp','.webp')){
  $target=Join-Path $OutputDir ('pagina_01'+$ext)
  Copy-Item -LiteralPath $InputPath -Destination $target -Force
  Write-Output ('FILE|'+$target)
  exit 0
}

if($ext -eq '.pptx'){
  $ppt=$null;$pres=$null;$workPres=$null;$localSource=$null;$localWork=$null
  try {
    $localSource=Join-Path $env:TEMP ('SR_EncarteImport_SRC_'+[Guid]::NewGuid().ToString('N')+'.pptx')
    $localWork=Join-Path $env:TEMP ('SR_EncarteImport_WORK_'+[Guid]::NewGuid().ToString('N')+'.pptx')
    Copy-Item -LiteralPath $InputPath -Destination $localSource -Force
    Copy-Item -LiteralPath $InputPath -Destination $localWork -Force

    $ppt=New-Object -ComObject PowerPoint.Application
    $ppt.Visible=-1
    $pres=$ppt.Presentations.Open($localSource,$true,$true,$false)
    if($pres.Slides.Count -lt 1){ Fail 'O PowerPoint não encontrou páginas/slides no arquivo importado.' }

    $totalShapes=0;$groups=0;$freeforms=0;$textShapes=0;$pictureShapes=0;$maxShapes=0
    for($si=1;$si -le $pres.Slides.Count;$si++){
      $sl=$pres.Slides.Item($si);$cnt=[int]$sl.Shapes.Count;$totalShapes+=$cnt;if($cnt -gt $maxShapes){$maxShapes=$cnt}
      for($j=1;$j -le $cnt;$j++){
        $sh=$sl.Shapes.Item($j);$type=[int]$sh.Type
        if($type -eq 6){$groups++}
        elseif($type -eq 5){$freeforms++}
        elseif($type -in @(11,13)){$pictureShapes++}
        if(-not [string]::IsNullOrWhiteSpace((Get-ShapeText $sh))){$textShapes++}
      }
    }
    $recommend='EDITABLE'
    $analysis=[ordered]@{
      pages=[int]$pres.Slides.Count; shapes=$totalShapes; max_shapes_per_page=$maxShapes; groups=$groups; freeforms=$freeforms;
      text_shapes=$textShapes; pictures=$pictureShapes; recommended=$recommend
    }
    $analysisPath=Join-Path $OutputDir 'analysis.json'
    ($analysis|ConvertTo-Json -Depth 6)|Set-Content -LiteralPath $analysisPath -Encoding UTF8
    Write-Output ('ANALYSIS|'+$analysisPath)
    if($Mode -eq 'ANALYZE'){ exit 0 }

    $slideW=[double]$pres.PageSetup.SlideWidth;$slideH=[double]$pres.PageSetup.SlideHeight
    $wh=Get-ExportSize $slideW $slideH;$exportW=[int]$wh[0];$exportH=[int]$wh[1]
    $sx=[double]$exportW/$slideW;$sy=[double]$exportH/$slideH

    if($Mode -eq 'FAITHFUL') {
      $manifest=[ordered]@{format='SR_CANVA_IMPORT';version=4;mode='FAITHFUL';recommended='EDITABLE';analysis=$analysis;pages=@()}
      for($si=1;$si -le $pres.Slides.Count;$si++) {
        $slide=$pres.Slides.Item($si)
        $background=Join-Path $OutputDir ('pagina_{0:D2}.png' -f $si)
        $slide.Export($background,'PNG',$exportW,$exportH)
        if(-not (Test-Path -LiteralPath $background)){ Fail ('Falha ao renderizar a página '+$si+' em modo fiel.') }
        Write-Output ('FILE|'+$background)
        $manifest.pages += [ordered]@{index=$si;background=$background;width=$exportW;height=$exportH;elements=@();faithful=$true}
      }
      $manifestPath=Join-Path $OutputDir 'import_manifest.json'
      ($manifest|ConvertTo-Json -Depth 14)|Set-Content -LiteralPath $manifestPath -Encoding UTF8
      Write-Output ('MANIFEST|'+$manifestPath);Write-Output 'INFO|MODE|FAITHFUL';Write-Output ('INFO|PAGES|'+$pres.Slides.Count)
      exit 0
    }

    $workPres=$ppt.Presentations.Open($localWork,$false,$false,$false)
    $manifest=[ordered]@{format='SR_CANVA_IMPORT';version=4;mode=$Mode;recommended='EDITABLE';analysis=$analysis;pages=@()}

    for($si=1;$si -le $workPres.Slides.Count;$si++){
      $slide=$workPres.Slides.Item($si)
      if($Mode -eq 'EDITABLE'){ $null=Flatten-Groups $slide }
      $elements=New-Object System.Collections.ArrayList
      $deleteIndices=New-Object System.Collections.ArrayList
      $shapeCount=[int]$slide.Shapes.Count

      for($j=1;$j -le $shapeCount;$j++){
        $sh=$slide.Shapes.Item($j);$type=[int]$sh.Type;$base=ShapeBase $sh $sx $sy;$txt=Get-ShapeText $sh;$handled=$false

        # Caixas de texto (msoTextBox=17) e placeholders com texto entram como texto nativo.
        if($Mode -eq 'EDITABLE' -and $type -in @(17,14) -and -not [string]::IsNullOrWhiteSpace($txt)){
          Add-TextElement $elements $sh $txt $sx $sy 0
          [void]$deleteIndices.Add($j);$handled=$true
        }

        # Formas simples tornam-se formas nativas do SR. Se houver texto, ele vira uma camada de texto independente.
        if(-not $handled -and $Mode -eq 'EDITABLE' -and $type -in @(1,9)){
          $shapeName='RECT'
          if($type -eq 9){$shapeName='LINE'}
          else {
            try{$ast=[int]$sh.AutoShapeType;if($ast -eq 5){$shapeName='ROUND'}elseif($ast -eq 9){$shapeName='CIRCLE'}else{$shapeName='RECT'}}catch{$shapeName='RECT'}
          }
          $fill='#FFFFFF';$outline='#000000';$weight=0;$radius=22
          try{$fill=HexFromRgb $sh.Fill.ForeColor.RGB '#FFFFFF'}catch{}
          try{$outline=HexFromRgb $sh.Line.ForeColor.RGB '#000000'}catch{}
          try{if([int]$sh.Line.Visible -ne 0){$weight=[Math]::Max(0,[double]$sh.Line.Weight*$sx)}}catch{}
          $el=[ordered]@{type='shape';shape=$shapeName;fill=$fill;outline=$outline;outline_width=[Math]::Round($weight,2);radius=$radius}
          foreach($k in $base.Keys){$el[$k]=$base[$k]}
          [void]$elements.Add($el)
          if(-not [string]::IsNullOrWhiteSpace($txt)){Add-TextElement $elements $sh $txt $sx $sy 1}
          [void]$deleteIndices.Add($j);$handled=$true
        }

        # Fotos e gráficos/vetores complexos viram objetos gráficos independentes.
        # Assim continuam fiéis ao PPTX, mas podem ser movidos, redimensionados, girados, duplicados e ordenados.
        if(-not $handled -and ($Mode -eq 'EDITABLE' -or $type -eq 6 -or $type -in @(11,13))){
          $asset=Join-Path $OutputDir ('slide_{0:D2}_shape_{1:D4}.png' -f $si,$j)
          if(Export-ShapePng $sh $asset){
            $el=[ordered]@{type='image';image=$asset;fit='contain';source_type=$type}
            foreach($k in $base.Keys){$el[$k]=$base[$k]}
            [void]$elements.Add($el);[void]$deleteIndices.Add($j);$handled=$true
          }
        }

        # HÍBRIDO: textos permanecem nativos; grupos/imagens viram objetos gráficos; o restante fica no fundo.
        if(-not $handled -and -not [string]::IsNullOrWhiteSpace($txt)){
          Add-TextElement $elements $sh $txt $sx $sy 0
          try{$slide.Shapes.Item($j).TextFrame2.TextRange.Text=''}catch{try{$slide.Shapes.Item($j).TextFrame.TextRange.Text=''}catch{}}
        }
      }

      # No EDITABLE tudo que foi extraído sai do fundo. Sobra apenas o background real do slide.
      $indices=@($deleteIndices|Sort-Object -Descending -Unique)
      foreach($idx in $indices){try{$slide.Shapes.Item([int]$idx).Delete()}catch{}}
      $background=Join-Path $OutputDir ('pagina_{0:D2}.png' -f $si)
      $slide.Export($background,'PNG',$exportW,$exportH)
      if(-not (Test-Path -LiteralPath $background)){ Fail ('Falha ao renderizar a página '+$si+' do modelo.') }
      Write-Output ('FILE|'+$background)
      $manifest.pages += [ordered]@{index=$si;background=$background;width=$exportW;height=$exportH;elements=@($elements);faithful=$false;editable=($Mode -eq 'EDITABLE')}
    }

    $manifestPath=Join-Path $OutputDir 'import_manifest.json'
    ($manifest|ConvertTo-Json -Depth 16)|Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Output ('MANIFEST|'+$manifestPath);Write-Output ('INFO|MODE|'+$Mode);Write-Output ('INFO|PAGES|'+$workPres.Slides.Count)
  } catch {
    Fail ('Falha ao importar PPTX pelo PowerPoint: '+$_.Exception.Message)
  } finally {
    if($workPres){try{$workPres.Close()}catch{}}
    if($pres){try{$pres.Close()}catch{}}
    if($ppt){try{$ppt.Quit()}catch{};try{[Runtime.InteropServices.Marshal]::ReleaseComObject($ppt)|Out-Null}catch{}}
    foreach($f in @($localSource,$localWork)){if($f){try{Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue}catch{}}}
    [GC]::Collect();[GC]::WaitForPendingFinalizers()
  }
  exit 0
}

if($ext -eq '.pdf'){
  $pdftoppm=(Get-Command pdftoppm -ErrorAction SilentlyContinue)
  if($pdftoppm){
    $prefix=Join-Path $OutputDir 'pagina'
    & $pdftoppm.Source -png -r 150 -- $InputPath $prefix | Out-Null
    $files=Get-ChildItem $OutputDir -Filter 'pagina-*.png' | Sort-Object Name
    $n=1
    foreach($f in $files){$target=Join-Path $OutputDir ('pagina_{0:D2}.png' -f $n);Move-Item -LiteralPath $f.FullName -Destination $target -Force;Write-Output ('FILE|'+$target);$n++}
    if($n -eq 1){ Fail 'O conversor PDF não gerou nenhuma página.' }
    exit 0
  }
  Fail 'PDF requer um conversor instalado. Exporte o modelo do Canva em PNG/JPG ou PPTX para importação garantida.'
}

$shown=if([string]::IsNullOrWhiteSpace($ext)){'(sem extensão)'}else{$ext}
Fail ('Formato não suportado: '+$shown+'. Use PNG, JPG, PPTX ou PDF.')
