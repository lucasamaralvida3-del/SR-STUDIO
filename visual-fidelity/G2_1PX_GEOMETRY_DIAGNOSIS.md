# G2 — diagnóstico do delta de 1 px

## Escopo

Exclusivamente **Novo Studio de Encartes G2**. Nenhum Golden Master ou código exclusivo do Gerador de Cartazes participa deste diagnóstico.

Nenhuma correção de renderer/importador foi aplicada nesta rodada. O objetivo é localizar a origem antes da baseline PNG oficial.

## Resultado

**1PX ROOT CAUSE: IDENTIFIED.**

O delta `[0,-1]` não nasce em `QImage`, `QSize`, devicePixelRatio, DPI nem em `floor()` no renderer. Ele já existe na geometria lógica produzida pelo importador a partir do tamanho de página do PPTX Canva.

### 1. PPTX / EMU

Os três documentos oficiais hashados usados nos 11 casos possuem exatamente o mesmo `p:sldSz`:

- `cx = 10,287,000 EMU`
- `cy = 12,852,400 EMU`

Como `1 pt = 12,700 EMU`:

- largura = `810 pt`
- altura = `1012 pt`

Uma página 4:5 exata com largura de 810 pt teria `1012.5 pt`. Portanto o próprio PPTX Canva está `0.5 pt` (`6,350 EMU`) abaixo da razão 4:5 usada pelos exports raster medidos.

### 2. Leitura PPTX

`src/srstudio/importers/pptx/reader.py::PptxImporter._presentation_size()` lê `cx/cy` como inteiros e preserva os valores acima. Não há perda por float nesta etapa.

### 3. Normalização do pipeline

`src/srstudio/importers/pipeline.py::UnifiedImportPipeline._pptx()` normaliza a página para largura lógica fixa de 1080 px:

```python
page.width = 1080.0
page.height = 1080.0 * (slide.height / max(slide.width, 1))
```

Com os EMUs oficiais:

```text
1080 * 12,852,400 / 10,287,000 = 1349.3333333333333
```

A SR Scene recebe, portanto:

```text
width  = 1080.0
height = 1349.3333333333333
unit   = px
```

Este é o ponto em que o G2 passa a carregar a altura que, quando rasterizada na largura da referência, ficará um pixel abaixo do export Canva 4:5.

### 4. target_width / DPI

`src/srstudio/graphics2/qt_renderer.py::_raster_scale()` prioriza `target_width`:

```python
if target_width:
    return int(target_width) / page.width
```

Portanto, no Fidelity Lab, DPI não participa do cálculo das dimensões quando `target_width` é informado.

Para 1080 px:

```text
scale = 1.0
raw height = 1349.3333333333333
round(...) = 1349
reference  = 1350
```

Para as páginas Quinta medidas a 1229 px:

```text
scale = 1229 / 1080
raw height = 1535.4913580246914
round(...) = 1535
reference  = 1536
```

### 5. Qt surface

Somente depois desses cálculos `render_png()` cria:

```python
QImage(width, height, QImage.Format_ARGB32_Premultiplied)
```

Logo o `QImage` recebe `1349` ou `1535`; ele não remove o pixel. Não existe `setDevicePixelRatio()` no caminho do renderer de produção analisado.

## Causas descartadas

- `floor` no lugar de `round`: **não**; o código usa `round`.
- truncamento `float -> int` no `QImage`: **não**; o inteiro já foi calculado antes.
- EMU lido incorretamente: **não**; os valores do `p:sldSz` são preservados.
- DPI: **não** no caminho `target_width` usado pelo reference suite.
- `QSize`: **não participa** da criação da superfície PNG analisada.
- `devicePixelRatio`: **não participa** desse caminho.
- Office Layout posterior: nenhuma etapa posterior altera o `page.height` antes do raster que explique o padrão 11/11.

## Arquivo/função responsável pelo aparecimento no G2

Primário:

`src/srstudio/importers/pipeline.py::UnifiedImportPipeline._pptx`

Downstream que materializa a dimensão já menor:

`src/srstudio/graphics2/qt_renderer.py::render_png`

A causa de origem é uma diferença de contrato entre o tamanho físico exportado pelo Canva no PPTX (`810 x 1012 pt`) e o canvas raster direto observado (4:5).

## Teste diagnóstico

Foi adicionado:

`tests/test_graphics2_g2_page_geometry_diagnostic.py`

Ele fixa três fatos sem corrigir o comportamento:

1. `10287000 x 12852400 EMU` produz Scene `1080 x 1349.333...`;
2. a 1080 px o renderer produz 1349, um abaixo de 1350;
3. a 1229 px produz 1535, um abaixo de 1536;
4. o caminho com `target_width` é independente de DPI.

A futura correção deverá atualizar deliberadamente esse teste somente **depois** da baseline PNG oficial ser congelada.

## Decisão desta rodada

**NÃO CORRIGIR AINDA.**

Qualquer solução precisa decidir explicitamente qual contrato é fonte da verdade para export raster de um Canva-PPTX: o `p:sldSz` físico ou a dimensão do export oficial. Essa decisão será tomada somente após as 11 referências PNG diretas existirem e a baseline PNG estar congelada.
