# CHAT 6 — EXPORTAÇÃO PNG + JPEG + PDF + OUTPUT FINAL

Atualizado em: 2026-08-17

## 1. Isolamento e baseline

- Repositório: `lucasamaralvida3-del/SR-STUDIO`
- Branch exclusiva: `g2/parallel-export-output`
- BASE_SHA: `89c91da05922d080453dcf42489dc671091bf671`
- Base de criação da branch: `g2/chatgpt-professional-usable`
- `main`/`stable`: não alterados por este CHAT 6.
- Merge de branches paralelas: nenhum.
- Reset/clean destrutivo: nenhum.
- Diff atual contra BASE_SHA antes deste arquivo: 20 commits, `ahead`, `behind_by=0`.

### Limitação do ambiente de execução

O ambiente desta sessão não disponibilizou um checkout Git local nem acesso de rede do container ao GitHub. Por isso não foi possível materializar fisicamente `../SR-STUDIO-g2-export-output` com `git worktree`. O isolamento foi aplicado diretamente no GitHub: a branch exclusiva foi criada exatamente no BASE_SHA e toda alteração foi gravada imediatamente como commit nessa branch. Não houve worktree principal local tocado e, por consequência, também não há alterações locais não commitadas deste agente para descartar.

Documentação de recuperação/arquitetura lida antes das mudanças:

- `AGENTS.md`
- `docs/SR_STUDIO_NEXT_ARCHITECTURE.md`
- `docs/G2_CONTINUOUS_PROGRESS.md`

`docs/G2_CONTINUOUS_PROGRESS.md` não foi editado.

## 2. Fronteira renderer x exportação

O `qt_renderer.py` visual não foi refatorado por este agente. A estratégia adotada foi uma camada posterior ao renderer:

- renderer continua responsável pela semântica visual do frame;
- `export_output.py` é responsável por formato, dimensão, DPI, alpha/background, arquivo, validação e publicação;
- `export_batch.py` é responsável pela transação de batch;
- `qt_render_runtime.py` conecta as chamadas históricas `qt_renderer.render_png/render_pdf` à camada segura, preservando o host atual sem editar QML do CHAT 3;
- qualquer divergência já presente no frame antes da saída continua sendo dependência do CHAT 1.

Isso separa explicitamente os dois diagnósticos exigidos:

1. **frame renderizado já está errado** → renderer/fidelidade, CHAT 1;
2. **frame correto foi alterado/invalidado durante output** → CHAT 6.

## 3. Bugs encontrados e severidade

### P1 — PNG transparente era efetivamente opaco no caminho legado

No renderer legado, `transparent=True` inicializava a `QImage` transparente, mas `_render_page(..., paint_background=transparent)` voltava a pintar o background da página. Resultado: a opção de transparência podia produzir PNG opaco.

**Correção:** a camada de output inicializa a superfície conforme a política escolhida e chama `_render_page(..., paint_background=False)`. O background da página não é repintado quando o usuário pede transparência; nós BACKGROUND explícitos continuam fazendo parte da cena.

### P1 — PDF era gravado diretamente no destino final

Uma exceção em uma página intermediária podia deixar um arquivo final parcial/truncado no caminho solicitado.

**Correção:** PDF é gerado em arquivo temporário irmão, validado e somente então publicado com `os.replace`. Um arquivo anterior não é substituído quando o renderer falha.

### P1 — PDF não provava que todas as páginas chegaram ao arquivo

O relatório do renderer informava `len(indices)`, mas a etapa final não reabria o PDF para confirmar número real de páginas.

**Correção:** reabertura com `pypdf`, validação de header `%PDF-`, `%%EOF`, contagem real e tamanho físico de cada página antes da publicação.

### P1 — JPEG não existia no contrato público G2 de saída

**Correção:** `export_jpeg()` com qualidade 1–100, dimensão exata/derivada, DPI metadata, fundo opaco configurável, extensão `.jpg/.jpeg`, validação por reabertura e publicação atômica.

### P1 — batch raster podia deixar conjunto parcial

O modelo original página-a-página publicava imediatamente. Uma falha na página N poderia deixar 1..N-1 aparentando um lote completo.

**Correção:** batch transacional em disco. Cada página é renderizada/validada sequencialmente em staging; somente após todas passarem o conjunto é publicado. Arquivos anteriores são movidos para backup durante a publicação e há rollback se uma página final não puder ser substituída.

### P1 — regressão interna descoberta durante esta missão na rota DPI-only

A primeira implementação de `_raster_geometry` usou um class body com `unit = unit`, que em Python causa `NameError` nessa forma. Casos com `target_width` passavam, mas o botão atual do Studio usa `dpi=300` sem largura explícita.

**Correção:** conversão direta por unidade (`mm → dpi/25.4`, `pt → dpi/72`, `px → dpi/96`) e teste dedicado para A4 300 DPI. A regressão foi encontrada e corrigida dentro desta branch antes de qualquer merge.

### P2 — risco de alocação raster gigante

DPI/custom size sem limite pode tentar reservar centenas de MB ou mais por QImage.

**Correção:** limite preventivo de 65.535 px por eixo e 100 milhões de pixels por raster. A4 600 DPI permanece permitido; saídas absurdas falham antes da alocação.

### P2 — nomes/overwrite/path pouco defensivos

**Correção:** normalização de extensão, criação de diretório, nomes reservados Windows (`CON`, `PRN`, `COM1` etc.), caracteres inválidos, `overwrite=False`, diretório usado como arquivo e publicação atômica.

### P2 — recurso ausente podia virar output aparentemente concluído

**Correção:** em `strict_assets=True` warnings fatais (`IMAGE_SOURCE_EMPTY`, `IMAGE_NOT_LOCAL`, `IMAGE_DECODE_FAILED`, `REMOTE_ASSET`) interrompem a publicação final.

## 4. Contratos implementados

### PNG

- single page;
- página escolhida por índice;
- target width;
- target height;
- largura + altura exatas apenas se preservarem aspect ratio;
- 1080×1350;
- custom size;
- A4 por DPI;
- DPI metadata via dots-per-meter;
- alpha real;
- background opaco quando transparência não é solicitada;
- validação por reabertura da imagem;
- extensão/naming/path;
- overwrite seguro;
- publicação atômica;
- limite de memória raster.

### JPEG

- single page;
- `.jpg` e `.jpeg`;
- qualidade 1–100;
- fundo opaco configurável;
- dimensão exata/derivada;
- DPI metadata;
- validação por reabertura;
- publicação atômica;
- batch transacional;
- naming previsível `*_p001.jpg`, `*_p002.jpg`, ...

### PDF

- single page;
- multipage;
- seleção/intervalo por `page_indices`;
- ordem solicitada preservada;
- seleção vazia rejeitada;
- índice inexistente rejeitado;
- duplicidade rejeitada;
- portrait/landscape;
- páginas de tamanhos diferentes no mesmo PDF;
- A4 físico;
- DPI de desenho sem alterar tamanho físico da página;
- header/EOF;
- reabertura;
- page count real;
- tamanho físico real por página;
- output temporário + publish atômico;
- falha intermediária não substitui PDF anterior;
- recursos fatais ausentes bloqueiam publicação.

### Batch raster

- PNG/JPEG;
- 3 páginas;
- 10 páginas;
- 25 páginas smoke;
- ordem de processamento preservada;
- nomes derivados do número real da página;
- nenhuma página duplicada na seleção;
- staging em disco;
- uma imagem por vez em memória;
- publicação somente após todas as páginas renderizarem;
- backup + rollback durante overwrite;
- callback de progresso `(completed, total, report)`.

## 5. Round-trip visual

Testes adicionados verificam:

- PNG exportado → QImage → dimensão, alpha, DPI e pixel de background;
- JPEG exportado → QImage → opacidade/background;
- PDF → `pypdf` → contagem/tamanho físico;
- PDF → `pypdfium2` → raster real → cor e ordem das páginas;
- três páginas de mesmo tamanho com backgrounds diferentes e ordem `[2, 0, 1]`, para que o teste não dependa apenas de MediaBox;
- PDF de uma única página selecionada;
- probes próximos aos quatro cantos para detectar margem implícita/scaling inesperado.

## 6. Testes criados

- `tests/test_graphics2_export_output.py`
  - 1080×1350;
  - alpha/DPI;
  - DPI-only A4 300;
  - custom height;
  - aspect ratio;
  - JPEG quality range/background;
  - A4 PDF;
  - PDF mixed portrait/landscape/square;
  - PDF 10 páginas;
  - seleção inválida;
  - projeto sem páginas;
  - path inválido;
  - repeat export;
  - overwrite false;
  - nomes Windows;
  - 25 páginas raster;
  - falha intermediária PDF;
  - page-loss report;
  - missing asset.
- `tests/test_graphics2_export_roundtrip.py`
  - PNG pixel round-trip;
  - PDFium page order/background;
  - seleção single page;
  - qualidade JPEG altera codificação;
  - recurso raster ausente;
  - falha renderer preserva destino anterior.
- `tests/test_graphics2_export_batch_transaction.py`
  - batch completo;
  - falha intermediária sem parcial;
  - preservação do batch anterior;
  - preflight overwrite false;
  - falha de publicação + rollback.
- `tests/test_graphics2_export_print_contract.py`
  - A4 landscape 300 DPI = 3508×2480;
  - unidade point (72 pt a 300 DPI = 300 px);
  - DPI PDF não altera tamanho físico A4;
  - background até bordas;
  - DPI inválido;
  - arquivo em uso no Windows preserva destino anterior.
- `tests/benchmark_graphics2_export_output.py`
  - bootstrap/primeiro PNG;
  - três repetições PNG;
  - batch PNG 10 páginas;
  - PDF 10 páginas;
  - A4 PNG 300 DPI;
  - pico de RSS por amostragem durante operação.

## 7. Performance — contrato para CHAT 5

O benchmark gera `g2-export-benchmark.json` com:

- `first_png_ms`;
- `repeat_png_mean_ms`;
- `repeat_png_min_ms`;
- `png_batch_total_ms`;
- `png_batch_per_page_ms`;
- `pdf_total_ms`;
- `pdf_per_page_ms`;
- `a4_300_ms`;
- `*_peak_rss_delta_mb`;
- `a4_300_width/height`;
- número de páginas efetivamente exportadas.

A implementação de batch não acumula QImages de todas as páginas: renderiza uma página, salva/valida no staging e libera a referência antes da próxima. O custo adicional da transação é armazenamento temporário em disco, não retenção de todas as imagens gigantes em RAM.

## 8. CI dedicado

Workflow: `.github/workflows/g2-export-output.yml`

Runner planejado: `windows-latest`, Python 3.11, extra `[dev,graphics2]`, `QT_QPA_PLATFORM=offscreen`.

Gate executa:

1. `compileall` dos módulos de export/runtime;
2. Ruff;
3. pytest das suítes de output + renderer já existente;
4. benchmark;
5. upload JUnit + benchmark JSON;
6. status explícito de commit `g2/export-output` com resumo de PNG10/PDF10/RSS.

### Estado de execução desta sessão

O container local desta sessão não possui PySide6 e não consegue baixar pacotes por DNS, portanto não é ambiente válido para executar os testes Qt. O conector GitHub disponível também não lista runs de `push` dessa branch; até a última consulta o status explícito `g2/export-output` ainda não apareceu. Consequentemente, **não registrar PASS de runtime sem evidência**. O código/testes foram commitados e o gate foi preparado para produzir uma evidência observável assim que o runner executar.

## 9. Matriz de pronto

| Critério | Implementação | Cobertura criada | Runtime observado nesta sessão |
|---|---|---|---|
| PNG | SIM | SIM | Aguardando gate Windows observável |
| JPEG | SIM | SIM | Aguardando gate Windows observável |
| PDF single-page | SIM | SIM | Aguardando gate Windows observável |
| PDF multipage | SIM | SIM | Aguardando gate Windows observável |
| Page order | SIM | SIM + PDFium | Aguardando gate Windows observável |
| Dimensions | SIM | SIM | Aguardando gate Windows observável |
| Error handling | SIM | SIM | Aguardando gate Windows observável |
| Repeat exports | SIM | SIM | Aguardando gate Windows observável |
| Large project smoke | SIM | 25 raster + 10 PDF | Aguardando gate Windows observável |

**P0 conhecido no código de output:** nenhum.

**P1 conhecido no código de output após as correções:** nenhum.

**Bloqueador de declaração formal de PASS:** evidência de execução do gate Qt/Windows, não um defeito funcional conhecido.

## 10. Dependências entre chats

### CHAT 1 — renderer/fidelidade

Nenhuma grande refatoração foi feita no renderer. Se o PDFium/PNG round-trip reproduzir exatamente o frame que já chega errado, a causa deve ser tratada no CHAT 1. A camada de output não deve compensar erro visual sistêmico do renderer.

### CHAT 3 — editor/QML

O host atual já chama os nomes históricos `qt_renderer.render_png/render_pdf`; o bootstrap foi redirecionado para o output seguro sem alteração de QML. JPEG e opções avançadas (qualidade, transparência, intervalo, batch) estão disponíveis no contrato Python, mas a exposição de novos controles/botões na UI deve ser coordenada com CHAT 3 para evitar conflito de QML.

### CHAT 5 — QA/performance

Consumir `tests/benchmark_graphics2_export_output.py` e o artefato `g2-export-benchmark.json` para séries de performance/stress. O CHAT 6 não edita a branch do CHAT 5.

## 11. Commits desta missão antes desta documentação

A branch estava 20 commits à frente do BASE_SHA. Commits principais/iterativos, em ordem de criação:

1. `3eb8675314bdd22e7c6dcbc757699602df79b6c0` — `feat(g2): add production-safe export output pipeline`
2. `272c36a5dc9a9fdf250ce6b04e1cd9d2ed492b1e` — `test(g2): cover PNG JPEG PDF and batch output contracts`
3. `a98ea1329fcc53a2e60cd4dcc8b2521b9f472342` — `ci(g2): validate parallel export output branch`
4. `e843a4748a5dc3f8e1a401feaaa44e383b184690` — `fix(g2): route host exports through safe output pipeline`
5. `59dd4935c22255b4a053db1601ac4b5b51a14649` — `fix(g2): validate DPI geometry and complete PDF output`
6. `cc79dca27a85815d45385ac4b22d7d0f3ba25bfb` — `test(g2): cover DPI-only host path and PDF no-loss gates`
7. `2736a6156265c189ee342fc8641b473bbe08f3f3` — `ci(g2): publish observable export gate status`
8. `5a7db2a9341203573d5fdc7cbb2b741b3b5c6ef9` — `test(g2): add reproducible export performance probe`
9. `c3c23137e135150ece3cd5e7a633c7961f2528af` — `fix(g2): make export benchmark portable`
10. `18d0699aec7c25d3fde0044429de6595ddde0594` — `ci(g2): measure export performance in output gate`
11. `f9d011b3f5e9a17b2ca2c56e8d9f723d9a79e263` — `test(g2): add visual round-trip and resource failure coverage`
12. `53a3af607a6a42a8c728bbf0ddf8646a011d8e62` — `ci(g2): gate export visual round-trip`
13. `80822707d1e795b682918739ca533da5ee1d2da5` — `feat(g2): make raster batch publication transactional`
14. `529573cfc1f959763a3310b1e80a1f75b07d7a50` — `fix(g2): install transactional raster batch contract`
15. `49537af4a476ce9a4ea2cbbb766375fdc3fb6f66` — `test(g2): prove transactional raster batch behavior`
16. `880799b0be95b94806df6e535d85820f4b4dded8` — `fix(g2): isolate batch publication primitive for rollback`
17. `1e05b8c1f35d3cb03a13937c827ed01f8e8e3f2a` — `test(g2): target final batch publication failure precisely`
18. `14bfa893682cff9ef7b061ffd60a648cfe288520` — `ci(g2): gate transactional batch output`
19. `b5543e52c5a5d7c40753e6fffc318c1a5a7a8f2f` — `test(g2): cover print dimensions DPI margins and locked output`
20. `52ce5658c6a8ef9ed0d28e3b28be6f79be8d7f5d` — `ci(g2): gate print output contracts`

## 12. Próximos passos seguros

1. Obter execução observável do workflow Windows/PySide6 e registrar números reais do benchmark.
2. Corrigir qualquer falha objetiva do gate dentro desta branch, mantendo a separação renderer/output.
3. Somente após PASS real, marcar a matriz obrigatória como PASS.
4. Coordenar com CHAT 3 a exposição UI de JPEG/qualidade/intervalo/batch, sem editar a branch dele.
