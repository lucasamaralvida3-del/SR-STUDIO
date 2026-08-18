# CHAT 7 — Build/Release, Integração e Baseline Visual do Studio de Encartes G2

Atualizado: 2026-08-18

## Escopo final

Esta missão é **exclusivamente do NOVO STUDIO DE ENCARTES G2**.

O Gerador de Cartazes legado é um produto separado. Seus módulos, UI, exportadores, templates e Golden Masters `CARTAZ_VENDA`, `SEGUNDA_DA_LIMPEZA*`, `CLUBE_EXCLUSIVO*` e `ATACADO` estão fora do critério de aceitação do Studio. Nenhum desenvolvimento do Gerador legado foi realizado nesta integração.

CHAT 8 permanece isolado e não foi integrado. `main` e `stable` não foram alteradas.

## HEAD funcional

- branch: `g2/integration-beta`
- base original: `15dbce6742066783c46db5599926f359cd125493`
- HEAD funcional validado: `d14dc5bed4bf4f7402f4668eb66a63823f48a35a`
- commits posteriores desta rodada: documentação/manifests/baseline visual; nenhum código funcional do produto foi alterado

## Integração funcional

Branches CHAT 1–6 foram incorporadas de forma controlada; CHAT 3 e CHAT 6 foram portados semanticamente por terem linhagem antiga. CHAT 8 não foi incorporado.

Gates finais do Studio:

| Área | Estado |
|---|---|
| Startup | PASS |
| Linux | PASS |
| Windows/Qt | PASS |
| Build/Release | PASS |
| Editor | PASS |
| Import PPTX/Canva | PASS |
| Renderer | PASS |
| Persistence | PASS |
| Autosave | PASS |
| Recovery | PASS |
| Multipage | PASS |
| ProductCards | PASS |
| PriceBlocks | PASS |
| Smart Slots | PASS |
| Bindings | PASS |
| PNG | PASS |
| JPEG | PASS |
| PDF single/multipage | PASS |
| E2E | PASS |
| Performance | PASS |
| Crash safety | PASS |

CHAT 5: Linux focado 34/34 PASS; Windows/Qt 60/60 PASS. CHAT 6: Linux + Windows/Qt PASS, 49 testes do contrato de export/regressão no Windows, frozen install/rollback PASS.

## Auditoria de escopo

A comparação `15dbce6...d14dc5b` contém G2 direto (`src/srstudio/graphics2/**`, workflows/testes/build Graphics2) e infraestrutura compartilhada necessária ao G2 (`pyproject.toml`, `diagnostics/crash_guard.py`, reader/order PPTX). **0 arquivos exclusivos do Gerador de Cartazes foram modificados.**

O PR #42, criado antes da correção de escopo para transportar os oito Golden Masters do Gerador legado, foi fechado sem merge e não introduziu código.

## Corpus visual próprio do G2

A baseline própria foi construída com **3 documentos reais / 11 páginas**, sem usar Golden Master do Gerador de Cartazes:

1. Quinta Filé — slides 12–15
   - PPTX SHA `7c45cfa205c7e14af69e41c8d63b1c6a9d1a06df3cf9d0131ed612029884e536`
   - Canva doc id `DAHMLMj6EH8`
2. Terça Verde — slides 5, 6 e 8
   - PPTX SHA `6e186a90c5591da2801d9049d5357755ab323f8d76b373104cbf757b0bc9c920`
   - Canva doc id `DAHMAeLZD3Q`
3. Quarta Café com Pão — slides 7–10
   - PPTX SHA `df20e5650711755cd9655b33eab2f72f0d7588f95c06bb34dca161dee2eae395`
   - Canva doc id `DAHMFY898gM`

Arquivos versionados:

- `visual-fidelity/g2-studio-corpus-v1.json`
- `visual-fidelity/g2-studio-corpus-v1-baseline.json`
- `visual-fidelity/g2-terca-verde-2026-08-11.json`
- `visual-fidelity/g2-quarta-cafe-2026-08-12.json`
- manifesto Quinta existente `visual-fidelity/quinta-file-13-08-2026.json`

### Imutabilidade / hash validation

Os 3 PPTX e as 11 referências recuperadas passaram SHA-256 e dimensões. Foi executado também um controle negativo: substituir a referência de Terça s05 pelos bytes de s06 produz `SHA-256 divergente` e o caso é rejeitado.

## Restrição de formato da referência

Os exports oficiais recuperados são **JPEGs diretos do Canva**, não PNGs. Os JPEGs Quarta e Terça s08 preservam XMP com `CreatorTool=Canva (Renderer)`, doc id coincidente com o PPTX e título da página. O Quinta bate exatamente com os hashes do manifesto G2 já versionado.

A regra atual exige PNG direto para aprovação final. Portanto nenhum JPEG foi convertido/renomeado para PNG e o corpus está versionado como:

`baseline_established_pending_png_reference`

Isso não invalida a medição quantitativa, mas impede chamar as referências atuais de corpus oficial v1 **aprovado**.

## Baseline quantitativa

Executada sobre o HEAD funcional congelado `d14dc5b...`:

- casos: 11
- hash validation: PASS
- min: **94,4183%**
- max: **97,7681%**
- mean: **95,9754%**
- median: **96,3717%**
- pixel pass médio: **87,0328%**
- changed area média: **12,9672%**
- render médio: **~601,9 ms/caso**
- regressões funcionais: **0**

Nenhum threshold do Gerador de Cartazes foi herdado. A baseline registra distribuição; acceptance threshold oficial do G2 continua **UNSET** até análise do corpus próprio.

### Finding sistêmico de dimensão

11/11 candidates saíram 1 px mais baixos que a referência:

- 1229×1535 vs 1229×1536; ou
- 1080×1349 vs 1080×1350.

Para calcular métricas sem modificar o renderer no meio da baseline, o laboratório apenas completou/cortou canvas até o tamanho da referência, **sem rescale**, mantendo `dimension_delta=[0,-1]` no relatório. O finding deve ser isolado entre page geometry do import e rounding do renderer antes de qualquer correção.

## Atribuição granular

Segunda passagem somente de laboratório: tile 32 px, hot-tile ≥10%, máximo 20 regiões; score/candidate não foram alterados.

Participação aproximada do gap visual:

- LAYERS: **53,18%**
- CROP: **30,13%**
- MASK: **12,45%**
- TEXT: **4,23%**

FONT/IMAGE/GROUP/SHAPE não receberam contribuição isolada pelo classificador atual. `WORDART`, `PRICE`, `PRODUCT` e `IMPORT` não são separados como classes independentes pelo classificador scene-aware atual e não devem ser tratados como ausentes. IMPORT/RENDER têm o finding transversal de 1 px em 11/11 casos.

## P0 / P1 / P2 / P3 — somente G2

- P0: **0**
- P1 funcional: **0**
- P2: **3**
  1. obter PNGs diretos para promover o corpus candidato a oficial v1 aprovado;
  2. isolar/corrigir o delta sistêmico de 1 px de altura;
  3. atacar sistemicamente LAYERS/CROP/MASK, que somam ~95,77% do gap atribuído
- P3: **0 confirmados**

## Classificação

- Functional readiness: **BETA FUNCIONAL — SIM**
- Visual readiness: **BASELINE ESTABLISHED**
- Corpus oficial v1 aprovado: **PENDENTE dos PNGs diretos exigidos pela regra atual**

## Próxima rodada recomendada

1. exportar/recuperar os mesmos 11 casos como PNG direto Canva/PowerPoint e registrar novos hashes sem sobrescrever os JPEGs históricos;
2. repetir a baseline com os PNGs oficiais;
3. isolar o rounding de altura 11/11;
4. corrigir por ordem sistêmica LAYERS → CROP → MASK;
5. expandir depois para transparência/rotação/grupos/fontes não instaladas/ProductCards quando houver referência oficial pareada.

Gerador de Cartazes e CHAT 8 permanecem fora desta rodada.
