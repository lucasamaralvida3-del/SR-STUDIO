# CHAT 7 — Build/Release e Integração Segura do Studio de Encartes G2

Atualizado: 2026-08-18

## Escopo final

Esta missão é **exclusivamente do NOVO STUDIO DE ENCARTES G2**.

O Gerador de Cartazes legado é um produto separado. Seus módulos, UI, exportadores, templates funcionais e os Golden Masters `CARTAZ_VENDA`, `SEGUNDA_DA_LIMPEZA*`, `CLUBE_EXCLUSIVO*` e `ATACADO` não fazem parte do critério de aceitação do Studio.

Artefatos históricos só podem ser usados como referência estática ou regression gate compartilhado quando necessário. Nenhum desenvolvimento do Gerador legado foi realizado nesta integração.

CHAT 8 permanece isolado e não foi integrado.

## Branch e HEAD funcional

- branch: `g2/integration-beta`
- base original da integração: `15dbce6742066783c46db5599926f359cd125493`
- HEAD funcional validado: `d14dc5bed4bf4f7402f4668eb66a63823f48a35a`
- `main`: não alterada
- `stable`: não alterada

## Branches incorporadas na Fase B

- `g2/parallel-import-office` — CHAT 2
- `g2/parallel-render-fidelity` — CHAT 1
- `g2/parallel-product-system` — CHAT 4
- `g2/parallel-editor-production` — CHAT 3, port semântico
- `g2/parallel-export-output` — CHAT 6, port semântico
- `g2/parallel-qa-performance` — CHAT 5, QA/test tooling

CHAT 8 não foi incorporado.

## Commits principais da integração controlada

Entre os checkpoints documentados:

- CHAT 1: `b4a398881b7acd6795fdcb74b5a0c9c5717d6d57`
- CHAT 4: `dfd75b532ace3c85cfeb33f924d510937a403223`
- Product compatibility estabilizada: `515651d3e79b6e9bf08b891799491b04d7240044`
- CHAT 3 persistence/autosave: `24e608ff69c77b7a7a9bac6fb3958ba5d6efc79e`
- CHAT 3 package/round-trip: `b9b7fc08ffa0229c2036d154d6f826dea66fec88`
- CHAT 3 QML/multipage/close guard: `bf7996d9ae183658123933be89342373668c0256`
- CHAT 3 validation tests: `b9d63020cd1aaa3715db1c64db4ddc67c15aec6d`
- CHAT 6 export modules: `03857fa1fde8844a4879b944cf15d54c5a1e5a8c`
- CHAT 6 output guard/bootstrap: `d972163397146a62181fce589f2badc5333edabf`
- CHAT 5 QA tooling: `6d11f34af248e448da5f85aee0f675464285848c`
- Gate global integrado: `d14dc5bed4bf4f7402f4668eb66a63823f48a35a`

## Auditoria de escopo

A comparação `15dbce6...d14dc5b` não contém alterações em arquivos exclusivos do Gerador de Cartazes.

### G2 direto

- `.github/workflows/g2-*`
- `build/*graphics2*`
- `src/srstudio/graphics2/**`
- `tests/test_graphics2_*`
- `tests/benchmark_graphics2_*`
- `tools/g2_*`

### Infraestrutura compartilhada usada pelo G2

- `pyproject.toml`
- `src/srstudio/diagnostics/crash_guard.py`
- `src/srstudio/importers/pptx/package_order.py`
- `src/srstudio/importers/pptx/reader.py`
- `tests/test_pptx_presentation_order.py`

Esses pontos compartilhados foram alterados somente por necessidade do G2 e passaram regressão.

### LEGACY

**0 arquivos exclusivos do Gerador de Cartazes modificados pela integração.**

O PR #42, aberto apenas para transportar o corpus dos Golden Masters posteriormente reconhecidos como fora de escopo, foi fechado sem merge e não introduziu código na integração.

## Gate funcional final do G2

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
| PDF single | PASS |
| PDF multipage | PASS |
| E2E | PASS |
| Performance smoke | PASS |
| Crash safety | PASS |

### CHAT 6

- Linux export: PASS
- Windows/Qt export: PASS
- Windows contract/regression: 49 tests PASS
- PNG/JPEG/PDF/batch/repeat/output-path/error handling: PASS
- frozen startup/install/rollback: PASS

### CHAT 5

- Linux focado: 34/34 PASS
- Windows/Qt focado: 60/60 PASS
- long-run save/load: sem crescimento material observado
- performance smoke: PASS

## Gate visual correto do G2

O gate visual do Studio está em `visual-fidelity/` e testa o **Graphics Engine 2**, não o Gerador de Cartazes.

Fluxo:

`PPTX/Canva real do encarte -> importador G2 -> SR Scene 2 -> qt_renderer G2 -> referência oficial estática -> Fidelity Lab/Triage`

O caso real versionado atual é `visual-fidelity/quinta-file-13-08-2026.json`, com quatro referências oficiais de Canva e SHA explícito do PPTX.

Testes pertencentes ao gate visual G2 incluem:

- `tests/test_graphics2_reference_suite.py`
- `tests/test_graphics2_fidelity_corpus.py`
- `tests/test_graphics2_fidelity_impact.py`
- renderer micro-fixtures de font-weight/group-opacity/transparency
- testes PPTX G2 de group transform, source crop, shape visual e text recovery

### Estado do corpus privado

O manifesto espera o PPTX SHA `7c45cfa205c7e14af69e41c8d63b1c6a9d1a06df3cf9d0131ed612029884e536`.

As duas cópias homônimas disponíveis na Biblioteca nesta auditoria produziram SHA diferentes (`8f57f0...` e `0353b8...`). Portanto elas não foram aceitas como substitutas silenciosas. As quatro referências oficiais hashadas também não foram recuperadas como conjunto completo nesta execução.

Resultado: **fidelidade visual G2 não classificada quantitativamente nesta rodada**. Isso não equivale a FAIL e não reutiliza os scores 83–93% do Gerador legado.

## P0 / P1 / P2 / P3 — somente Studio G2

- P0: **0**
- P1 funcional impeditivo: **0**
- P2: **1** — executar o corpus visual G2 correto com o PPTX e referências privadas exatamente hashados, ou criar um novo manifesto para um encarte G2 real atual
- P3: **0 confirmados nesta auditoria**

## Classificação final desta integração

### Functional readiness

**BETA FUNCIONAL: SIM.**

A matriz funcional principal está verde em Linux e Windows/Qt e não há P0/P1 funcional conhecido.

### Visual readiness

**PENDENTE DE EVIDÊNCIA QUANTITATIVA PRÓPRIA DO STUDIO.**

Não usar os oito Golden Masters do Gerador de Cartazes para promoção ou bloqueio do G2.

## Próximo bloqueador exclusivamente do Studio

Restaurar o corpus privado do gate `Quinta Filé` exatamente hashado — ou estabelecer um novo corpus oficial de Encartes G2 com PPTX/Canva + exportações de referência — e executar `reference_suite` para criar a baseline visual própria do Studio.

Nenhuma nova funcionalidade do Gerador de Cartazes deve ser desenvolvida como parte dessa rodada.
