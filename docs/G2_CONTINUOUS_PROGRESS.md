# G2 Continuous Progress — SR Studio de Encartes

Atualizado: 2026-08-18

## Escopo obrigatório

**O produto desta missão é exclusivamente o NOVO STUDIO DE ENCARTES G2.**

Inclui SR Graphics Engine 2, SR Scene 2, editor Qt/QML G2, importação PPTX/Canva do Studio, Office Layout usado pelo G2, renderer G2, ProductCards, PriceBlocks, Smart Slots, bindings, multipágina, persistência, autosave/recovery, export, build/release e QA do G2.

O **Gerador de Cartazes legado é outro produto e não faz parte do desenvolvimento desta rodada**. Os oito Golden Masters históricos `CARTAZ_VENDA`, `SEGUNDA_DA_LIMPEZA*`, `CLUBE_EXCLUSIVO*` e `ATACADO` pertencem exclusivamente ao Gerador de Cartazes e não são gate de aceitação, fidelidade ou Beta do Studio G2.

CHAT 8 / Image Database continua isolado e não está incluído nesta integração.

## Estado integrado

- Branch: `g2/integration-beta`
- HEAD funcional validado: `d14dc5bed4bf4f7402f4668eb66a63823f48a35a`
- HEAD anterior somente de documentação: `d3e7507bf3bf023f0dc5cf7b027e285284ab844c`
- CHAT 1–6: integrados; CHAT 5 e CHAT 6 PASS
- CHAT 8: **não integrado**
- `main` / `stable`: não alteradas

## Readiness funcional — estado real

O HEAD funcional `d14dc5b...` permanece verde nos gates do Studio:

| Área | Estado |
|---|---|
| Startup | PASS |
| Linux | PASS |
| Windows/Qt | PASS |
| Build/Release | PASS |
| Editor G2 | PASS |
| Import PPTX/Canva G2 | PASS |
| Renderer G2 | PASS |
| Save/Load | PASS |
| Round-trip SR Scene 2 | PASS |
| Autosave | PASS |
| Recovery | PASS |
| Multipágina | PASS |
| ProductCards | PASS |
| PriceBlocks | PASS |
| Smart Slots | PASS |
| Bindings | PASS |
| PNG | PASS |
| JPEG | PASS |
| PDF single-page | PASS |
| PDF multipage | PASS |
| E2E | PASS |
| Regression G2 | PASS |
| Performance smoke | PASS |
| Crash safety | PASS |

### Evidência QA / export

- CHAT 5 Linux focado: 34/34 PASS
- CHAT 5 Windows/Qt focado: 60/60 PASS
- long-run Linux 30 save/load: crescimento RSS observado ~0,15 MB
- Windows long-run/harness: crescimento RSS observado 0 MB nessa execução
- PNG Windows: mediana observada ~54 ms
- PDF multipágina de 10 páginas: ~21,6 ms por iteração no harness reportado
- CHAT 6 export Linux + Windows/Qt: PASS
- PNG/JPEG/PDF/batch/repeat/path/error handling: PASS
- frozen build / instalação / rollback: PASS

## Auditoria de escopo

Comparação funcional auditada: `15dbce6742066783c46db5599926f359cd125493..d14dc5bed4bf4f7402f4668eb66a63823f48a35a`.

### G2

- `.github/workflows/g2-*.yml`
- `build/*graphics2*`
- `src/srstudio/graphics2/**`
- `tests/test_graphics2_*.py`
- `tests/benchmark_graphics2_*.py`
- `tools/g2_*.py`
- documentação das missões G2

### Infraestrutura compartilhada necessária ao G2

- `pyproject.toml`
- `src/srstudio/diagnostics/crash_guard.py`
- `src/srstudio/importers/pptx/package_order.py`
- `src/srstudio/importers/pptx/reader.py`
- `tests/test_pptx_presentation_order.py`

### LEGACY

**Nenhum arquivo exclusivamente do Gerador de Cartazes legado foi modificado no delta integrado.**

## Corpus visual próprio do Studio G2 — baseline candidata v1

A primeira baseline visual própria do Studio foi construída sem usar qualquer Golden Master do Gerador de Cartazes.

### Documentos selecionados

1. `OFERTAS QUINTA FILÉ NOVO (1).pptx`
   - SHA-256: `7c45cfa205c7e14af69e41c8d63b1c6a9d1a06df3cf9d0131ed612029884e536`
   - Canva document identifier no PPTX: `DAHMLMj6EH8`
   - 4 páginas medidas: slides 12–15
2. `OFERTAS TERÇA VERDE NOVO.pptx`
   - SHA-256: `6e186a90c5591da2801d9049d5357755ab323f8d76b373104cbf757b0bc9c920`
   - Canva document identifier: `DAHMAeLZD3Q`
   - 3 páginas medidas: slides 5, 6 e 8
3. `OFERTAS QUARTA CAFÉ COM PÃO NOVO.pptx`
   - SHA-256: `df20e5650711755cd9655b33eab2f72f0d7588f95c06bb34dca161dee2eae395`
   - Canva document identifier: `DAHMFY898gM`
   - 4 páginas medidas: slides 7–10

Total: **3 documentos / 11 páginas reais**.

Os documentos foram recuperados do corpus real `Downloads(1)(1).zip`. O Quinta Filé recuperado bate exatamente com o SHA que já estava registrado em `visual-fidelity/quinta-file-13-08-2026.json`.

### Referências recuperadas

Foram recuperados exports oficiais limpos do Canva correspondentes às páginas selecionadas. Para Quarta Café e Terça Verde slide 8, o próprio JPEG preserva XMP com `CreatorTool=Canva (Renderer)`, document identifier coincidente com o PPTX e título de página correspondente. O Quinta Filé bate byte a byte com os hashes históricos do manifesto G2 existente.

**Importante:** os arquivos oficiais recuperados são JPEG, enquanto a missão atual exige PNG direto de Canva/PowerPoint para aprovação final do corpus. Nenhum JPEG foi convertido/renomeado para fingir conformidade. Portanto:

- baseline quantitativa real: **ESTABELECIDA**;
- corpus oficial v1 aprovado: **PENDENTE dos PNGs diretos**;
- status versionado: `baseline_established_pending_png_reference`.

### Hash validation

**PASS para todos os 3 PPTX e 11 JPEGs oficiais usados na baseline candidata.**

O mecanismo G2 `reference_suite` rejeita fonte PPTX com SHA divergente e também rejeita referência cuja SHA/dimensão não corresponda ao manifesto. A nova baseline mantém a mesma propriedade de imutabilidade.

## Baseline quantitativa — 11 casos

Medição feita sobre o HEAD funcional congelado `d14dc5bed4bf4f7402f4668eb66a63823f48a35a`:

- score mínimo: **94,4183%**
- score máximo: **97,7681%**
- média: **95,9754%**
- mediana: **96,3717%**
- pixel pass médio: **87,0328%**
- changed area média: **12,9672%**
- render médio observado: **~601,9 ms/caso**
- regressões funcionais: **0**

Nenhum threshold de outro produto foi promovido a gate. Os valores atuais são distribuição de baseline; `FidelityPolicy` existente foi usado apenas para calcular métricas comparáveis, não para declarar PASS/FAIL oficial.

| Caso | Score | Pixel pass | Changed area | Candidate size | Render |
|---|---:|---:|---:|---|---:|
| Quinta s12 | 94,5157% | 82,4941% | 17,5059% | 1229×1535 | 2054,5 ms |
| Quinta s13 | 94,9060% | 84,3516% | 15,6484% | 1229×1535 | 453,9 ms |
| Quinta s14 | 94,4183% | 81,8881% | 18,1119% | 1229×1535 | 469,8 ms |
| Quinta s15 | 96,4772% | 89,6350% | 10,3650% | 1229×1535 | 496,4 ms |
| Terça Verde s05 | 95,5706% | 84,7350% | 15,2650% | 1080×1349 | 396,8 ms |
| Terça Verde s06 | 96,3717% | 86,9997% | 13,0003% | 1080×1349 | 391,9 ms |
| Terça Verde s08 | 97,7422% | 93,5986% | 6,4014% | 1080×1349 | 443,0 ms |
| Quarta Café s07 | 95,0775% | 84,7337% | 15,2663% | 1080×1349 | 368,7 ms |
| Quarta Café s08 | 96,4502% | 87,6683% | 12,3317% | 1080×1349 | 317,0 ms |
| Quarta Café s09 | 96,4323% | 88,4553% | 11,5447% | 1080×1349 | 631,2 ms |
| Quarta Café s10 | 97,7681% | 92,8016% | 7,1984% | 1080×1349 | 597,1 ms |

### Diferença geométrica sistêmica observada

**11/11** renders saíram com a mesma largura da referência e **1 pixel a menos de altura**:

- 1229×1535 vs 1229×1536; ou
- 1080×1349 vs 1080×1350.

Para permitir medição do conteúdo sem alterar o renderer no meio da baseline, o laboratório completou somente o canvas faltante/cortou eventual overflow **sem escala**. O delta dimensional original continua registrado e não foi mascarado.

Esse problema é a primeira frente a isolar entre `IMPORT` (page geometry/aspect) e `RENDER` (rounding de tamanho de saída), mas não houve correção nesta rodada.

## Atribuição aproximada das divergências

A primeira triagem padrão agregava grandes regiões conectadas e era grosseira. Foi feita uma segunda passagem **somente de laboratório**, sem alterar score/candidata/produto, usando tiles de 32 px, hot-tile ≥10% e até 20 regiões por página.

Participação aproximada do gap visual medido:

| Categoria | Participação aproximada |
|---|---:|
| LAYERS | **53,18%** |
| CROP | **30,13%** |
| MASK | **12,45%** |
| TEXT | **4,23%** |
| FONT | 0% atribuído por sinal específico |
| IMAGE | 0% isolado |
| GROUP | 0% isolado |
| SHAPE | 0% isolado |
| RENDER | 0% nas regiões normalizadas; há o delta de dimensão 11/11 fora deste rateio |

`WORDART`, `PRICE`, `PRODUCT` e `IMPORT` não são categorias separadas pelo classificador scene-aware atual. Não se deve interpretar isso como prova de ausência. `IMPORT/RENDER` possuem evidência transversal própria na diferença de 1 px em 11/11 casos. Nenhuma região ficou sem suspeito scene-aware na segunda passagem.

## Top divergences desta baseline

1. **Geometria de página / rounding:** 11/11 páginas ficam 1 px abaixo da referência oficial.
2. **LAYERS:** ~53,18% do gap visual atribuído após triagem granular.
3. **CROP:** ~30,13%.
4. **MASK:** ~12,45%.
5. **TEXT:** ~4,23%.

A prioridade visual mudou em relação aos números antigos do Gerador de Cartazes: esses números não pertencem ao G2 e não são usados aqui.

## P0 / P1 / P2 / P3 — somente G2

### P0

**0 conhecidos.**

### P1 funcional

**0 conhecidos.**

### P2

1. **Visual:** isolar/corrigir a diferença sistêmica de 1 px de altura sem regredir layout.
2. **Corpus:** recuperar/exportar PNGs diretos do Canva/PowerPoint para promover a baseline candidata a corpus oficial v1 conforme a regra atual.
3. **Visual:** investigar primeiro LAYERS/CROP/MASK porque explicam ~95,77% do gap visual atribuído na primeira baseline própria do Studio.

### P3

**0 confirmados nesta rodada.**

## Classificação

### Functional readiness

**BETA FUNCIONAL: SIM.**

### Visual readiness

**BASELINE ESTABLISHED — corpus oficial v1 ainda pendente de referência PNG conforme a regra atual.**

Os scores 94,42–97,77% descrevem somente estes 11 encartes reais G2 e não são comparados a thresholds herdados do Gerador de Cartazes.

## Próxima prioridade exclusivamente do Studio

1. obter os 11 PNGs diretos correspondentes às referências Canva/PowerPoint, preservando os JPEGs atuais como evidência histórica e nunca sobrescrevendo hashes;
2. reexecutar a mesma baseline sem normalização de formato;
3. isolar o delta de altura entre page geometry importada e cálculo de output do renderer;
4. depois atacar sistemicamente LAYERS → CROP → MASK;
5. ampliar o corpus com outro documento real que cubra transparência/rotação/grupos/fontes não instaladas/ProductCards quando houver referência oficial correspondente;
6. manter todo Gerador de Cartazes e seus Golden Masters fora deste processo.
