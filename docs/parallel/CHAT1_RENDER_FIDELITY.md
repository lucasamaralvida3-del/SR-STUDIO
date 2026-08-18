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

Relatório histórico usado sem rerender desnecessário: `SR_STUDIO_ALPHA_29_FINAL_ASSESSMENT.md` + relatórios Alpha 30–34 já persistidos.

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
- regressão dedicada cobre 100,200,...,900 e clamps/default.

### Teste/gates

- testes dedicados adicionados em `tests/test_graphics2_qt_renderer_font_weight.py`;
- SR Graphics Engine 2 CI: PASS;
- SR Studio 5 Quality: PASS;
- G2 Alpha 43 Validation: PASS;
- Windows Qt Quick: PASS no primeiro ciclo.

### Limitação para o corpus atual

O import bridge ainda reduz a origem PPTX a `font_weight = 700 if bold else 400`; portanto o renderer agora está correto para pesos 800/900, mas o corpus PPTX só colherá esse ganho quando CHAT 2 preservar o peso efetivo da fonte/run.

## Ciclo 2 — desempenho por Golden Master

### Patch

- `c482507de5263aa4a80c30cd0b50a6d1fb0f2ec6` — `feat(graphics2): measure reference render performance`
- `1f1d19aea27f3b8384a4993573c85621a04b8963` — teste do resumo de timing.

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
- clip_path vira MASK;
- contratos visuais em ancestral group viram GROUP;
- forte ambiguidade de z-order vira LAYERS;
- sem nó associado vira RENDER.

## Auditoria WordArt / escala física — P1 sistêmico

Foram inspecionados os PPTX reais `CLUBE PROMO EXCLUSIVO.pptx`, `CARTAZ AMARELO FONTE 2 - Copia.pptx` e `Cartazes Atacarejo SR (1)(2).pptx` diretamente no OOXML, sem alterar o importador.

Todos usam `p:sldSz cx=5400675 cy=7559675`, aproximadamente 5,90625 pol de largura. A pipeline converte a geometria para página lógica de 1080 px, fator de escala de aproximadamente 1,9048 em relação a 96 dpi, mas `_pptx_element()` mantém o `font_size_pt` original e a SR Scene não conserva `sldSz`/escala física em `GraphicsPage.metadata`.

Nos elementos dominantes também foi confirmado:

- `bodyPr fromWordArt="1"`;
- `prstTxWarp prst="textPlain"`;
- tamanhos base recorrentes de 36,16 pt e 40 pt;
- caixas de WordArt muito maiores que o ink produzido por texto Qt comum;
- outline DrawingML presente, por exemplo `a:ln w=9525` em tokens de preço.

Conclusão: o problema dominante não é um simples DPI constante do QPainter. A geometria PPTX foi normalizada sem transportar o contrato físico/WordArt suficiente para o renderer reproduzir PowerPoint de forma determinística. Não foi aplicado um multiplicador fixo ~1,90x porque isso seria template-specific e arriscaria regressão, repetindo o problema observado na Alpha 34.

### Evidência contra patch amplo

A Alpha 34 já mostrou que ativar um caminho Full-Spec amplo melhorou 10/10 microfixtures mas regrediu CARTAZ_VENDA em aproximadamente -0,8588 p.p.; a maior ablação isolada foi vertical anchor/line-box, ~-2,1851 p.p. Portanto qualquer nova ativação de WordArt/autofit deve entrar em patch pequeno + A/B em CARTAZ_VENDA primeiro.

## GROUP/alpha — divergência renderer↔preview confirmada, P2 no corpus atual

`GraphicsEditor.qml` calcula opacidade efetiva multiplicando ancestrais. O QPainter atualmente usa somente `node.opacity` e pula nodes GROUP durante desenho. Um filho dentro de group com opacity != 1 pode renderizar com alpha incorreto.

Não foi priorizado antes de TEXT/WORDART porque a telemetria do corpus histórico registra efeitos/alpha praticamente ausentes e apenas dois casos com group reconstruído. Corrigir genericamente continua recomendado depois do P1 tipográfico ou quando um Golden Master apontar GROUP como região dominante.

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
   - arquivos: `src/srstudio/importers/pipeline.py`, `src/srstudio/graphics2/import_bridge.py`
   - funções: `_pptx_element()`, `_convert_visual_page()`.
   - causa: x/y/w/h são normalizados para 1080 px; `font_size_pt` permanece absoluto; `GraphicsPage.metadata` não registra `sldSz` nem scale-from-source.
   - reprodução: PPTX real com `cx=5400675`; 36,16 pt mantém 36,16 no style embora toda geometria tenha sido ampliada para 1080 px.
   - correção sugerida: transportar `source_slide_width_emu`, `source_slide_height_emu`, escala lógica e metadados WordArt/run; não bakear fator específico do template.
   - impacto estimado: P1, pois WORDART+TEXT somam 94,20% do diff atribuído.

3. **WordArt não identificado semanticamente para o renderer**
   - causa: OOXML real tem `fromWordArt=1` + `prstTxWarp=textPlain`, mas esses contratos não aparecem no style/metadata consumido por `qt_renderer._draw_text()`.
   - correção sugerida: preservar flag WordArt, preset warp, outline/fill por run e transformação necessária no SR Scene.
   - impacto: P1, especialmente ATACADO e CLUBE.

### CHAT 3 — QML/editor

- arquivo: `src/srstudio/graphics2/qml/GraphicsEditor.qml`
- causa: `font.bold: font_weight >= 700` também colapsa 800/900 para Bold 700.
- reprodução: Scene `font_weight=900` aparece como Bold no preview.
- correção sugerida: usar peso numérico Qt equivalente.
- impacto: preview/export podem divergir em peso quando CHAT 2 começar a preservar 800/900.

## CI do HEAD atual

HEAD validado antes desta atualização documental: `53bb9b7d5be1adc8406463b3cb44e8e3fb11f5f6`.

- SR Studio 5 Quality — PASS (`32086225506`)
- SR Graphics Engine 2 CI — PASS (`32086225519`)
- G2 Alpha 43 Validation — PASS (`32086225582`)

O branch está 11 commits à frente do BASE_SHA, 0 atrás, sem merge em `main`/`stable`.

## Próximo ciclo recomendado

1. Consumir metadados de WordArt/escala física assim que CHAT 2 os preservar; começar por CARTAZ_VENDA como A/B de aceitação.
2. Implementar no renderer a composição específica `textPlain`/outline/line-box em passos independentes, nunca como backend inteiro de uma vez.
3. Medir antes/depois com `reference_suite` novo: score + render_ms + região + impact category.
4. Só depois rerodar os outros sete casos.
5. Corrigir ancestor GROUP opacity como P2 isolado com regressão pixel-level.
