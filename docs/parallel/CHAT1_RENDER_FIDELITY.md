# CHAT 1 — Renderer + Fidelidade Visual + Golden Masters

## Isolamento

- Branch: `g2/parallel-render-fidelity`
- Worktree solicitado: `../SR-STUDIO-g2-render-fidelity`
- BASE_SHA: `15dbce6742066783c46db5599926f359cd125493`
- Base: `integration/sr-studio-next`
- PR de validação: `#26` (draft; não fazer merge durante a missão paralela).
- O checkout local do repositório não estava montado no ambiente desta sessão e o acesso Git direto não resolvia `github.com`; por isso o isolamento foi estabelecido no branch remoto conectado, sem tocar em `main`, `stable` ou no worktree principal.

## Estado inicial confirmado

- Crash `0xC0000409`: causa já conhecida no harness/CLI por ausência de `QGuiApplication` antes de `render_png()`.
- No HEAD atual o bootstrap já existe indiretamente no caminho público: `render_png()` chama `register_qt_document_fonts()`, que chama `ensure_qgui_application()`. Não foi reaberta nem duplicada a correção do crash.
- Com `QGuiApplication`, os 8 Golden Masters completam; o bloqueador é fidelidade, não performance.
- Thresholds não foram reduzidos nem baselines trocados.

## Baseline real recuperado dos artefatos existentes

Relatórios históricos usados sem rerender desnecessário: `SR_STUDIO_ALPHA_29_FINAL_ASSESSMENT.md` e relatórios Alpha 30–34 persistidos.

| Caso | Score | Pixel pass | Área alterada |
|---|---:|---:|---:|
| CARTAZ_VENDA | 93,5798% | 91,0219% | 8,9781% |
| SEGUNDA_DA_LIMPEZA_1_PRECO | 87,0321% | 81,4083% | 18,5917% |
| SEGUNDA_DA_LIMPEZA_2_PRECOS | 86,6813% | 79,7286% | 20,2714% |
| SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE | 85,9904% | 78,7399% | 21,2601% |
| CLUBE_EXCLUSIVO_COM_LIMITE | 84,8268% | 78,1837% | 21,8163% |
| SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE | 84,6447% | 77,9573% | 22,0427% |
| ATACADO | 84,3857% | 74,8494% | 25,1506% |
| CLUBE_EXCLUSIVO | 83,2605% | 75,6407% | 24,3593% |

Estado: 0/8 passam score >= 98,5%, pixel pass >= 96,5% e changed area <= 3,5%.

### Performance existente

Harness existente, sem recalcular Golden Masters:

- import + criação da cena: 9,6–21,5 ms; média 17,0 ms;
- save `.srscene`: 3,4–14,7 ms; média 10,6 ms;
- open `.srscene`: 14,2–19,0 ms; média 16,2 ms;
- render PNG 2160 px: 293,1–316,6 ms; média 309,2 ms;
- PDF 300 dpi: 8,5–80,8 ms; média 46,2 ms;
- total: 328,9–447,1 ms; média 399,2 ms;
- working set máximo: 82,047 MB.

Performance continua P3/observacional; fidelidade é P1.

## Atribuição dominante já medida

O Attribution Lab Alpha 32 repartiu pixels divergentes por bounding box/z-order:

- WORDART: 6.230.748 pixels = 60,48%;
- TEXT: 3.473.515 pixels = 33,72%;
- IMAGE: 500.416 pixels = 4,86%;
- UNATTRIBUTED: 96.768 pixels = 0,94%;
- SHAPE: 0 nessa atribuição.

TEXT + WORDART = 94,20% dos pixels atribuídos. A atribuição é um proxy espacial, não causalidade exata, mas é forte o suficiente para priorizar tipografia/layout antes de grandes alterações de IMAGE/CROP/GROUP.

Maiores regiões/nós históricos incluem aproximadamente:

- ATACADO / WordArt: ~7,505 p.p. estimados;
- CLUBE_EXCLUSIVO / WordArt: ~6,042 p.p.;
- CLUBE_EXCLUSIVO_COM_LIMITE / WordArt: ~6,041 p.p.;
- CARTAZ_VENDA / maior TEXT: ~4,550 p.p.

## Ciclo 1 — FONT: preservar peso real no renderer

### Causa

`qt_renderer._draw_text()` usava `font.setBold(font_weight >= 700)`. Isso transforma 800/900 (ExtraBold/Black) em Bold 700 e perde informação tipográfica antes da rasterização.

### Patch

- `ce42388edf3081cf9ffd88dde5244d9eb6a1b780` — `fix(graphics2): preserve renderer font weight`
- `_set_font_weight()` preserva a escala CSS/DrawingML 100..900 via `QFont.Weight`.
- regressão dedicada cobre 100, 200, ..., 900 e clamps/default.

### Teste/gates

- testes dedicados em `tests/test_graphics2_qt_renderer_font_weight.py`;
- SR Graphics Engine 2 CI: PASS;
- SR Studio 5 Quality: PASS;
- G2 Alpha 43 Validation: PASS;
- Windows Qt Quick: PASS.

### Limitação para o corpus atual

O import bridge ainda reduz a origem PPTX a `font_weight = 700 if bold else 400`; portanto o renderer agora está correto para pesos 800/900, mas o corpus PPTX só colherá esse ganho quando CHAT 2 preservar o peso efetivo da fonte/run.

## Ciclo 2 — desempenho por Golden Master

### Patches

- `c482507de5263aa4a80c30cd0b50a6d1fb0f2ec6` — `feat(graphics2): measure reference render performance`
- `1f1d19aea27f3b8384a4993573c85621a04b8963` — regressão do resumo de timing.

`reference_suite.py` agora persiste, sem alterar thresholds:

- `render_ms` por caso;
- `elapsed_ms` por render;
- total/média/mínimo/máximo do renderer;
- resumo no console.

## Ciclo 3 — classificação FONT/TEXT/IMAGE/CROP/MASK/GROUP/LAYERS/SHAPE/RENDER

### Patches

- `56c7b5a464d17ab4b7d036466d56411c1603f017` — `feat(graphics2): classify fidelity impact by render category`
- `58ff83804cb89604da00830441a479f5cf175afc` — integração no Reference Suite;
- testes em `tests/test_graphics2_fidelity_impact.py` e `tests/test_graphics2_reference_suite.py`.

Cada caso passa a gerar `*-impact.json` com:

- categoria provável;
- P1/P2/P3;
- número de regiões;
- importância medida;
- share do diff;
- perda de score estimada em pontos percentuais.

A perda estimada reparte o gap global proporcionalmente à importância do triage. É explicitamente uma métrica de priorização; não afirma que um patch recuperará exatamente aqueles pontos.

Regras conservadoras:

- texto só vira FONT se existir sinal concreto de família substituída/peso não padrão/fonte ausente;
- spacing/wrap/alinhamento ficam TEXT;
- imagem com crop/fillRect/cover/zoom vira CROP;
- `clip_path` vira MASK;
- contratos visuais em ancestral group viram GROUP;
- forte ambiguidade de z-order vira LAYERS;
- sem nó associado vira RENDER.

## Ciclo 4 — agregação transversal do corpus

### Patches

- `37a3fe250df39ad38395f46536c66429000bc668` — `feat(graphics2): aggregate fidelity causes across corpus`;
- `9a5d4dfeceacc3b0348b3d25b9a4e75bc0a1f079` — `test(graphics2): cover systemic fidelity aggregation`.

Novo módulo `src/srstudio/graphics2/fidelity_corpus.py` agrega múltiplos relatórios de impacto e responde automaticamente quais causas são sistêmicas nos Golden Masters. O relatório inclui:

- casos afetados por categoria;
- regiões;
- importância acumulada;
- perda de score estimada acumulada;
- participação no gap do corpus;
- maior prioridade observada;
- `systemic_categories` para causas presentes em pelo menos dois casos e com share relevante do gap.

Isso elimina a necessidade de analisar manualmente os oito `impact.json` após a próxima execução real do corpus.

## Auditoria OOXML dos oito PPTX fonte — P1 sistêmico

Foram inspecionados os PPTX reais diretamente no OOXML, sem alterar o importador e sem tratar screenshots auxiliares como Golden Masters.

| Fonte/caso | Text shapes | WordArt `fromWordArt=1` | `textPlain` | WordArt com outline | Escala física aproximada para página lógica 1080 px |
|---|---:|---:|---:|---:|---:|
| CARTAZ_VENDA | 14 | 12 | 12 | 12 | 1,9048x |
| SEGUNDA_DA_LIMPEZA_1_PRECO | 12 | 10 | 10 | 10 | 1,5000x |
| SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE | 12 | 10 | 10 | 10 | 1,5000x |
| SEGUNDA_DA_LIMPEZA_2_PRECOS | 15 | 13 | 13 | 13 | 1,9132x |
| SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE | 15 | 13 | 13 | 13 | 1,9132x |
| CLUBE_EXCLUSIVO | 12 | 10 | 10 | 10 | 1,9048x |
| CLUBE_EXCLUSIVO_COM_LIMITE | 18 | 14 | 14 | 14 | 1,9048x |
| ATACADO — fonte multipágina (93 slides) | 1.767 | 1.395 | 1.395 | 1.395 | 1,9048x |

Achados compartilhados:

- `bodyPr fromWordArt="1"` é dominante nos textos que mais perdem score;
- o corpus observado usa `prstTxWarp prst="textPlain"`, não warps exóticos;
- praticamente todo WordArt auditado possui outline DrawingML;
- largura de outline recorrente: `a:ln w="9525"`, equivalente a ~0,75 pt / ~1 px lógico a 96 dpi antes da escala da cena;
- Algerian é a família dominante nas caixas WordArt auditadas;
- tamanhos base recorrentes: 36,16 pt, 40 pt e valores próximos;
- os fatores físicos de normalização variam de 1,50x a 1,9132x entre templates.

### Conclusão sobre escala

A pipeline converte x/y/w/h da geometria PPTX para uma página lógica de 1080 px, mas mantém `font_size_pt` como valor absoluto e a SR Scene não conserva o `p:sldSz`/escala física da origem em `GraphicsPage.metadata`.

Para uma conversão materializada em pixels lógicos, a relação exata é:

`font_size_logical_px = font_size_pt * 12700 * (page_logical_width / source_slide_width_emu)`

onde 1 pt = 12.700 EMU. Alternativamente, CHAT 2 pode preservar `source_slide_width_emu`, `source_slide_height_emu` e a escala original e deixar o renderer aplicar o contrato explicitamente.

Não foi aplicado um multiplicador fixo de ~1,90x no renderer porque isso quebraria os templates cuja relação é 1,50x ou 1,9132x. Um fator hard-coded seria template-specific e repetiria a classe de regressão já observada no piloto Full-Spec.

### Conclusão sobre WordArt/outline

O renderer atual não tem como reproduzir corretamente o WordArt se a Scene não identificar que o texto veio de `fromWordArt=1`, qual `prstTxWarp` foi usado e qual stroke/fill pertence a cada run.

O outline também se perde antes do renderer: `_draw_text()` recebe apenas o fill/cor comum e o bridge atual não transporta `a:rPr/a:ln` como contrato de stroke tipográfico. O problema é repetido em todos os WordArts auditados, mas permanece P2 isoladamente; os dados históricos mostram BOX_LAYOUT/AUTOFIT/transformação de WordArt como P1 maior.

## Evidência contra patch amplo de texto

A Alpha 34 já mostrou que ativar um caminho Full-Spec amplo melhorou 10/10 microfixtures, mas regrediu CARTAZ_VENDA de 93,579777% para 92,720982% (-0,858795 p.p.). A maior ablação isolada foi vertical anchor/line-box, aproximadamente -2,185127 p.p.

Portanto:

- não ativar backend completo por preferência arquitetural;
- manter Qt como raster de produção;
- corrigir layout Office em componentes pequenos;
- validar primeiro em CARTAZ_VENDA;
- só executar os outros sete após ganho sem regressão.

## GROUP/alpha — divergência renderer↔preview confirmada, P2 no corpus atual

`GraphicsEditor.qml` calcula opacidade efetiva multiplicando ancestrais. O QPainter atualmente usa somente `node.opacity` e pula nodes GROUP durante desenho. Um filho dentro de group com opacity != 1 pode renderizar com alpha incorreto.

Não foi priorizado antes de TEXT/WORDART porque a telemetria do corpus histórico registra IMAGE em apenas 4,86% do diff classificado, nenhum sinal novo de perda de shape/z-order e apenas dois grupos reconstruídos, ambos sem membros não associados. Corrigir genericamente continua recomendado depois do P1 tipográfico ou quando um Golden Master apontar GROUP como região dominante.

## Dependências dos outros chats

### CHAT 2 — importação PPTX/Canva

1. **Peso de fonte colapsado**
   - arquivo: `src/srstudio/graphics2/import_bridge.py`
   - função: `_style_from_element()`
   - causa: `font_weight` vira apenas 400/700 a partir de `bold`.
   - reprodução: fonte/run 800 ou 900 chega à SR Scene como 700.
   - correção sugerida: transportar peso efetivo do run/theme para a Scene.
   - impacto: limita diretamente o patch de FONT do CHAT 1.

2. **Escala física da página não chega à Scene**
   - arquivos: `src/srstudio/importers/pipeline.py`, `src/srstudio/graphics2/import_bridge.py`.
   - funções: `_pptx_element()`, `_convert_visual_page()`.
   - causa: x/y/w/h são normalizados para 1080 px; `font_size_pt` permanece absoluto; `GraphicsPage.metadata` não registra `sldSz` nem scale-from-source.
   - reprodução: os oito fontes têm fatores físicos diferentes, aproximadamente 1,50x, 1,9048x e 1,9132x.
   - correção sugerida: transportar `source_slide_width_emu`, `source_slide_height_emu`, escala lógica e/ou materializar `font_size` em pixels lógicos a partir da mesma transformação da geometria.
   - impacto estimado: P1, pois WORDART+TEXT somam 94,20% do diff atribuído.

3. **WordArt não identificado semanticamente para o renderer**
   - arquivos suspeitos: `src/srstudio/importers/pipeline.py`, `src/srstudio/graphics2/pptx_fidelity.py`, `src/srstudio/graphics2/import_bridge.py`.
   - causa: OOXML real tem `fromWordArt=1` + `prstTxWarp=textPlain`, mas esses contratos não aparecem no style/metadata consumido por `qt_renderer._draw_text()`.
   - reprodução: 12/14 textos no CARTAZ, 10/12 nos CLUBE/SEGUNDA 1 preço, 13/15 nos SEGUNDA 2 preços e 1.395/1.767 no fonte ATACADO são WordArt.
   - correção sugerida: preservar flag WordArt, preset warp, transform, runs, defaults herdados e vínculo com outline/fill.
   - impacto: P1, especialmente ATACADO e CLUBE.

4. **Outline tipográfico por run não é transportado**
   - arquivos suspeitos: `src/srstudio/importers/pipeline.py`, `src/srstudio/graphics2/pptx_fidelity.py`, `src/srstudio/graphics2/import_bridge.py`.
   - causa: `a:rPr/a:ln`, inclusive `w="9525"`, não chega ao style/metadata que o renderer usa.
   - reprodução: todos os WordArts auditados nos oito fontes possuem outline.
   - correção sugerida: preservar stroke color/alpha/width/join por run, sem convertê-lo em glyph-path prematuramente.
   - impacto: P2 isolado; repetição sistêmica e pré-requisito para paridade final.

### CHAT 3 — QML/editor

- arquivo: `src/srstudio/graphics2/qml/GraphicsEditor.qml`;
- causa: `font.bold: font_weight >= 700` também colapsa 800/900 para Bold 700;
- reprodução: Scene `font_weight=900` aparece como Bold no preview;
- correção sugerida: usar peso numérico Qt equivalente;
- impacto: preview/export podem divergir em peso quando CHAT 2 começar a preservar 800/900.

## CI do último HEAD de código

HEAD de código validado: `9a5d4dfeceacc3b0348b3d25b9a4e75bc0a1f079`.

- SR Studio 5 Quality — PASS (`32086861948`)
- SR Graphics Engine 2 CI — PASS (`32086862041`)
  - compile: PASS;
  - runtime lint gate: PASS;
  - Visual Fidelity/Production Gate: PASS;
  - Fidelity Lab/Triage/Golden Master/Reference Suite CLI smokes: PASS;
  - Graphics Engine 2 tests: PASS;
  - full SR Studio regression suite: PASS;
  - Windows Qt Quick job: PASS.
- G2 Alpha 43 Validation — PASS (`32086862089`)
  - Ubuntu G2: PASS;
  - Windows Qt: PASS.

Antes deste commit exclusivamente documental, o branch estava 14 commits à frente do BASE_SHA e 0 atrás. Nenhum merge em `main` ou `stable` foi feito.

## Score antes/depois desta sessão

Não foi inventado delta de Golden Master.

Os artefatos históricos existentes foram suficientes para recuperar scores, performance, regiões dominantes e priorização. Os PNG/JSON brutos do run atual dos oito Golden Masters não estavam montados no ambiente do CHAT 1, e o worktree local também não estava disponível; por isso o corpus completo não foi rerenderizado cegamente.

Além disso, o primeiro patch de FONT preserva 800/900 no renderer, mas o bridge atual entrega somente 400/700 para o corpus PPTX. Logo, atribuir qualquer aumento de score real a esse patch sem o handoff do CHAT 2 seria incorreto.

## Próximo ciclo recomendado

1. CHAT 2 preservar escala física, WordArt, runs, peso real e outline no SR Scene.
2. CHAT 1 consumir esses metadados no renderer em patches independentes: primeiro escala/transformação `textPlain`, depois line-box/anchor, depois outline/run composition.
3. Usar CARTAZ_VENDA como A/B inicial; o patch só avança se superar 93,579777% sem piorar pixel pass, changed area ou TEXT loss.
4. Medir com o Reference Suite novo: score + `render_ms` + região + categoria + perda estimada.
5. Somente após CARTAZ_VENDA melhorar, rerodar os outros sete e usar `fidelity_corpus.py` para ordenar causas sistêmicas restantes.
6. Corrigir ancestor GROUP opacity como P2 isolado com regressão pixel-level após o P1 de WordArt/BOX_LAYOUT.
