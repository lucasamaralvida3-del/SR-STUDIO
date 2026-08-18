# CHAT 6 — EXPORTAÇÃO PNG + JPEG + PDF + OUTPUT FINAL

Atualizado em: 2026-08-17

## 1. Estado final

**STATUS DO CHAT 6: PASS para o pipeline de output G2 no escopo desta branch.**

Gate final observado no Windows/PySide6, commit de medição:

- `453fcf39fcfd49372cb22006e5cb2687ce3a5370`
- `g2/export/install = success`
- `g2/export/compile = success`
- `g2/export/lint = success`
- `g2/export/test-core = success`
- `g2/export/test-roundtrip = success`
- `g2/export/test-batch = success`
- `g2/export/print-a4 = success`
- `g2/export/print-point = success`
- `g2/export/print-pdf-size = success`
- `g2/export/print-edges = success`
- `g2/export/print-dpi = success`
- `g2/export/print-lock = success`
- `g2/export/test-legacy = success`
- `g2/export/benchmark = success`
- `g2/export-output = success`

**P0 conhecido no output:** nenhum.

**P1 conhecido no output após as correções:** nenhum.

## 2. Isolamento e baseline

- Repositório: `lucasamaralvida3-del/SR-STUDIO`
- Branch exclusiva: `g2/parallel-export-output`
- BASE_SHA: `89c91da05922d080453dcf42489dc671091bf671`
- Base usada para criar a branch: `g2/chatgpt-professional-usable`
- `main`/`stable`: não alterados pelo CHAT 6.
- Merge de outras branches: nenhum.
- Reset/clean destrutivo: nenhum.
- `docs/G2_CONTINUOUS_PROGRESS.md`: lido, mas não editado.

Arquivos obrigatórios lidos antes das alterações:

- `AGENTS.md`
- `docs/SR_STUDIO_NEXT_ARCHITECTURE.md`
- `docs/G2_CONTINUOUS_PROGRESS.md`

### Worktree

O ambiente desta sessão não forneceu um checkout Git local do repositório e o container não tinha acesso de rede ao GitHub para criar fisicamente `../SR-STUDIO-g2-export-output`. Para não tocar no worktree principal, o isolamento foi feito na branch remota exclusiva criada exatamente no BASE_SHA; todas as alterações foram commitadas diretamente nessa branch. Não houve alteração local não commitada nem alteração de `main`/`stable` por este agente.

## 3. Fronteira renderer x output

O CHAT 6 não fez grande refatoração da semântica visual do renderer.

Responsabilidades mantidas:

- `qt_renderer.py`: semântica visual da cena;
- `export_output.py`: formato, dimensão, DPI, alpha/background, nomes, paths, validação e publicação atômica;
- `export_batch.py`: staging, publicação transacional e rollback de batch;
- `pdf_output_renderer.py`: somente adaptação do paint device PDF — tamanho físico, margens, background full-bleed e transição de páginas;
- `qt_render_runtime.py`: integração do host existente com o pipeline seguro.

Regra de diagnóstico:

1. frame já errado antes da saída → CHAT 1 / renderer/fidelidade;
2. frame correto alterado, truncado, escalado ou publicado incorretamente → CHAT 6.

## 4. Bugs encontrados e corrigidos

### P1 — PNG transparente podia sair opaco

O caminho legado preenchia a `QImage` com transparência e depois voltava a pintar o background da página durante `_render_page`.

Correção:

- superfície PNG transparente é inicializada com alpha;
- background implícito da página não é repintado;
- nós `BACKGROUND` explícitos continuam sendo conteúdo normal da cena;
- round-trip confirma canal alpha e pixel transparente.

### P1 — PDF podia deixar arquivo final parcial

O renderer legado escrevia diretamente no path final.

Correção:

- render em arquivo temporário irmão;
- validação completa antes da publicação;
- `os.replace` somente após sucesso;
- erro em página intermediária preserva o PDF anterior.

### P1 — perda silenciosa de páginas não era detectada

Correção:

- validação de header `%PDF-`;
- validação de `%%EOF`;
- reabertura com `pypdf`;
- contagem real de páginas;
- tamanho físico real de cada página;
- divergência impede publicação.

### P1 — JPEG não existia no contrato de output G2

Correção:

- `export_jpeg()`;
- qualidade configurável 1–100;
- `.jpg` e `.jpeg`;
- resolução customizada;
- DPI metadata;
- background opaco configurável;
- validação por reabertura;
- publicação atômica;
- batch transacional.

### P1 — batch raster podia ficar parcialmente publicado

Correção:

- cada página é renderizada e validada sequencialmente em staging;
- nenhuma página final é publicada até todas passarem;
- arquivos anteriores são movidos para backup durante overwrite;
- falha na publicação de uma página dispara rollback;
- não é necessário manter todas as QImages do lote simultaneamente na memória.

### P1 — regressão DPI-only encontrada dentro da própria missão

A primeira implementação nova de `_raster_geometry` possuía um `NameError` no caminho que não recebia `target_width`.

Impacto potencial:

- o botão atual do Studio chama PNG com `dpi=300`, então a regressão quebraria o fluxo real.

Correção:

- conversão direta por unidade:
  - mm → `dpi / 25.4`;
  - pt → `dpi / 72`;
  - px → `dpi / 96`;
- teste específico A4 300 DPI.

### P1 — PDF final tinha área não pintada nas bordas

O primeiro gate real isolou uma única falha na suíte de impressão: `print-edges`.

Diagnóstico:

- A4 raster PASS;
- unidade point PASS;
- tamanho físico PDF PASS;
- DPI PASS;
- arquivo bloqueado PASS;
- somente full-bleed/borda falhava.

Correção:

- `pdf_output_renderer.py` configura margens PDF em zero antes de iniciar cada página;
- o background é pintado diretamente na área física do `QPdfWriter` antes da escala uniforme da cena;
- a cena continua usando o mesmo renderer visual;
- evita faixa de borda causada pelo paint rect/margens e arredondamentos do dispositivo.

Validação após correção, commit `d4890c17b7176aedff1a11e6900cf7d1e001befc`:

- `print-edges = success`;
- core = success;
- round-trip = success;
- batch = success;
- renderer legado = success;
- benchmark = success.

### P2 — risco de alocação raster excessiva

Correção:

- máximo de 65.535 px por eixo;
- máximo de 100.000.000 pixels por raster;
- erro acontece antes da criação de uma QImage absurda.

### P2 — paths/naming/overwrite pouco defensivos

Correção:

- extensão normalizada;
- criação de diretórios;
- `overwrite=False`;
- nomes reservados Windows (`CON`, `PRN`, `COM1`, etc.);
- caracteres inválidos;
- diretório usado como arquivo;
- parent path inválido;
- arquivo em uso no Windows;
- publicação atômica.

### P2 — recurso ausente podia produzir output aparentemente concluído

Com `strict_assets=True`, os seguintes warnings bloqueiam publicação:

- `IMAGE_SOURCE_EMPTY`;
- `IMAGE_NOT_LOCAL`;
- `IMAGE_DECODE_FAILED`;
- `REMOTE_ASSET`.

## 5. Contratos validados

### PNG

PASS:

- single page;
- página por índice;
- 1080×1350;
- A4 por DPI;
- custom width;
- custom height;
- width + height compatíveis;
- rejeição de distorção de aspect ratio;
- alpha real;
- background opaco;
- DPI metadata;
- reabertura do arquivo;
- naming;
- extensão;
- path;
- overwrite;
- repeat export;
- limite preventivo de memória.

### JPEG

PASS:

- single page;
- dimensão exata/derivada;
- `.jpg` e `.jpeg`;
- qualidade 1–100;
- qualidade altera efetivamente a codificação;
- background opaco;
- DPI metadata;
- naming;
- extensão incorreta normalizada;
- batch de 10 páginas sem duplicação/nem perda;
- publicação transacional.

### PDF

PASS:

- single page;
- multipage;
- 3 páginas em round-trip visual;
- 10 páginas smoke;
- ordem solicitada;
- seleção de página;
- seleção fora de ordem;
- duplicidade rejeitada;
- seleção vazia rejeitada;
- índice inexistente rejeitado;
- portrait;
- landscape;
- páginas com tamanhos diferentes no mesmo PDF;
- A4 físico;
- DPI sem alterar o tamanho físico;
- background full-bleed;
- ausência de margem implícita detectável pelo teste;
- header/EOF;
- contagem real;
- tamanho físico real por página;
- falha intermediária sem substituir output anterior;
- recurso obrigatório ausente bloqueia publicação.

### Batch raster

PASS:

- 3 páginas;
- 10 páginas;
- 25 páginas smoke;
- PNG;
- JPEG;
- ordem;
- naming previsível `*_p001`, `*_p002`, ...;
- intervalos/seleções mantendo número real da página;
- nenhuma duplicação;
- nenhuma página faltando;
- staging em disco;
- rollback de publicação;
- preservação de batch anterior;
- callback de progresso.

## 6. Round-trip visual

PASS:

- PNG → QImage → dimensão/alpha/DPI/background;
- JPEG → QImage → dimensão/opacidade/background;
- PDF → `pypdf` → páginas/tamanho físico;
- PDF → `pypdfium2` → raster real;
- três páginas de mesmo tamanho com backgrounds distintos em ordem `[2, 0, 1]`;
- uma única página selecionada;
- probes próximos aos quatro cantos para detectar margem ou scaling de saída.

## 7. Performance medida no runner Windows

Benchmark: `tests/benchmark_graphics2_export_output.py`.

Medições observadas no commit `453fcf39fcfd49372cb22006e5cb2687ce3a5370`:

| Medida | Resultado |
|---|---:|
| Primeiro PNG 1080×1350 | 165,54 ms |
| Batch PNG 10 páginas | 551,43 ms |
| PNG médio no batch | 55,14 ms/página |
| PDF 10 páginas | 125,80 ms |
| PDF médio | 12,58 ms/página |
| A4 PNG 300 DPI | 329,76 ms |
| Delta de RSS observado durante batch PNG | 0 MB |
| Delta de RSS observado durante PDF | 0 MB |

Nota sobre RSS: o benchmark mede **delta de working set em relação ao baseline imediatamente anterior a cada operação**. O valor 0 MB significa que, nessa execução e resolução de amostragem, não houve aumento adicional observável do working set acima do baseline já aquecido; não significa consumo total de memória igual a zero.

A estratégia de batch continua sequencial: uma página é renderizada/salva/validada por vez; o conjunto completo fica em staging em disco, não como uma coleção de QImages gigantes simultâneas.

## 8. Suítes/gates

Workflow:

- `.github/workflows/g2-export-output.yml`
- `windows-latest`
- Python 3.11
- extra `[dev,graphics2]`
- `QT_QPA_PLATFORM=offscreen`

O gate executa:

1. instalação;
2. compileall;
3. Ruff;
4. core output;
5. visual round-trip;
6. batch transacional;
7. A4 landscape;
8. unidade point;
9. tamanho físico PDF;
10. full-bleed PDF;
11. DPI inválido;
12. arquivo bloqueado;
13. regressões do renderer Qt existente;
14. benchmark.

Arquivos principais de teste:

- `tests/test_graphics2_export_output.py`
- `tests/test_graphics2_export_roundtrip.py`
- `tests/test_graphics2_export_batch_transaction.py`
- `tests/test_graphics2_export_print_contract.py`
- `tests/test_graphics2_qt_renderer.py`
- `tests/benchmark_graphics2_export_output.py`

## 9. Matriz obrigatória de pronto

| Critério | Estado |
|---|---|
| PNG | **PASS** |
| JPEG | **PASS** |
| PDF single-page | **PASS** |
| PDF multipage | **PASS** |
| Page order | **PASS** |
| Dimensions | **PASS** |
| Error handling | **PASS** |
| Repeat exports | **PASS** |
| Large project smoke test | **PASS** |

## 10. Dependências dos outros agentes

### CHAT 1 — renderer/fidelidade

Se uma divergência já existe no frame antes do output, continua pertencendo ao CHAT 1. O CHAT 6 não introduziu compensações para problemas visuais sistêmicos do renderer.

### CHAT 3 — editor/QML

O host atual continua chamando os nomes históricos `qt_renderer.render_png` e `qt_renderer.render_pdf`, agora redirecionados para o pipeline seguro.

JPEG, qualidade JPEG, transparência, seleção/intervalo e batch estão disponíveis no contrato Python. A exposição de novos controles/botões na UI deve ser coordenada com o CHAT 3 para não criar conflito de QML/editor.

### CHAT 5 — QA/performance

Pode consumir diretamente:

- `tests/benchmark_graphics2_export_output.py`;
- o artefato `g2-export-benchmark.json`;
- os status `g2/bench/*` publicados pelo workflow.

## 11. Commits relevantes

BASE:

- `89c91da05922d080453dcf42489dc671091bf671`

Implementação/testes iniciais:

- `3eb8675314bdd22e7c6dcbc757699602df79b6c0` — production-safe output pipeline;
- `272c36a5dc9a9fdf250ce6b04e1cd9d2ed492b1e` — PNG/JPEG/PDF/batch tests;
- `e843a4748a5dc3f8e1a401feaaa44e383b184690` — host → safe output;
- `59dd4935c22255b4a053db1601ac4b5b51a14649` — DPI geometry + PDF validation;
- `cc79dca27a85815d45385ac4b22d7d0f3ba25bfb` — DPI-only + page-loss gates;
- `f9d011b3f5e9a17b2ca2c56e8d9f723d9a79e263` — visual round-trip;
- `80822707d1e795b682918739ca533da5ee1d2da5` — transactional batch;
- `b5543e52c5a5d7c40753e6fffc318c1a5a7a8f2f` — print contracts.

Diagnóstico/fix final de impressão:

- `99ad5af271595055c7de4bf82ab257a0377b842a` — gate diagnóstico por suíte;
- `2c54ae53134cc11562e89b787a947aa3fb57fc2f` — isolamento dos contratos de impressão;
- `0d3d8de0eb3a43a434a5483e35b2b2cebdd107e9` — PDF full-bleed paint-device adapter;
- `d4890c17b7176aedff1a11e6900cf7d1e001befc` — integração do adaptador PDF; gate funcional completo PASS;
- `453fcf39fcfd49372cb22006e5cb2687ce3a5370` — métricas observáveis; gate e benchmark PASS.

## 12. Resultado para produto

No escopo de output, o G2 agora possui contrato confiável para gerar arquivos destinados a:

- WhatsApp/compartilhamento raster;
- Instagram 1080×1350;
- armazenamento em PNG/JPEG/PDF;
- impressão A4;
- PDF single e multipágina;
- exportação batch.

Os arquivos não são publicados como sucesso quando a validação detecta truncamento, perda de páginas, dimensão física divergente, recurso obrigatório ausente ou falha durante a publicação.
