# CHAT 1 — Renderer + Fidelidade Visual + Golden Masters

## Isolamento

- Branch: `g2/parallel-render-fidelity`
- Worktree solicitado: `../SR-STUDIO-g2-render-fidelity`
- BASE_SHA: `15dbce6742066783c46db5599926f359cd125493`
- Base: `integration/sr-studio-next`
- O checkout local do repositório não estava montado no ambiente desta sessão e o acesso Git direto não resolvia `github.com`; por isso o isolamento foi estabelecido no branch remoto conectado, sem tocar em `main`, `stable` ou no worktree principal.

## Estado inicial conhecido

- Crash `0xC0000409`: causa já confirmada no harness/CLI por ausência de `QGuiApplication` antes de `render_png()`. Não reinvestigar do zero.
- Com `QGuiApplication` explícita, os 8 Golden Masters completaram.
- Todos os 8 falharam fidelidade; faixa informada: aproximadamente `83,2605%` a `93,5798%`.
- Thresholds não serão reduzidos.

## Evidência histórica útil

- O gate sintético de imagem/crop/fillRect/máscara/flip já demonstrou paridade preview↔renderer >= 99,5% em teste dedicado. Isso reduz a prioridade inicial de alterações amplas em IMAGE/CROP/MASK, sem provar que os 8 casos reais estejam livres dessas divergências.
- Pendências históricas explícitas do renderer incluem tipografia, `nowrap`/auto-fit e métricas/spacing de texto. A investigação inicial prioriza FONT/TEXT por potencial sistêmico.

## Ciclo 1 — auditoria tipográfica

### Hipótese inicial

`qt_renderer._draw_text()` converte `font_size` em pontos para pixels lógicos e chama `QFont.setPixelSize(round(...))`. A quantização inteira pode alterar métricas de glifos, largura, baseline e wrapping para tamanhos fracionários, propagando divergência em muitos nós de texto.

### Próximos testes mínimos

1. Confirmar a unidade e o contrato de `font_size`, `letter_spacing`, `line_spacing_px` e `line_spacing_percent` nos testes/fixtures atuais.
2. Confirmar se a quantização inteira é observável em teste isolado de métricas antes de qualquer patch.
3. Se confirmada, aplicar patch mínimo somente no renderer + teste de regressão.

## Dependências de outros chats

Nenhuma confirmada neste ponto. Se a origem do erro for importação/mapeamento PPTX, registrar aqui e encaminhar ao CHAT 2 sem grande alteração naquela área.
