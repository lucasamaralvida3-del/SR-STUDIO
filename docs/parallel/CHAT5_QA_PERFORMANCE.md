# CHAT 5 — QA + Performance + Stress

## Isolamento

- Branch: `g2/parallel-qa-performance`
- BASE_SHA: `15dbce6742066783c46db5599926f359cd125493`
- Linha-base: `integration/sr-studio-next`
- Worktree solicitado: `../SR-STUDIO-g2-qa-performance`
- Restrição do ambiente desta execução: o repositório não está montado localmente e o shell não possui resolução de rede para clonar o GitHub. Por isso, a isolação foi materializada como branch remota criada diretamente do BASE_SHA; execução de testes e benchmarks é delegada ao GitHub Actions desta branch. Nenhum worktree principal, `main` ou `stable` foi alterado.
- `AGENTS.md`: não encontrado no snapshot remoto acessível desta linha-base. As regras explícitas da missão do Chat 5 continuam sendo tratadas como autoridade.

## Ambiente de QA

O workflow `G2 QA Performance` usa Ubuntu, Python 3.11 e instala `.[dev,graphics2]`, incluindo PySide6. O Qt é executado com `QT_QPA_PLATFORM=offscreen`.

## Cobertura herdada confirmada

A linha-base já contém testes dedicados para autosave/recovery, round-trip de bridge, package stress, clone/delete de páginas, PDF multipágina, ProductCard duplicate, project actions e um E2E de encarte real com ProductCards, bindings, edição, move/resize, duplicate/delete, undo/redo, save/reopen, autosave/recovery e exportações Qt.

## Infraestrutura adicionada pelo Chat 5

### `tests/test_graphics2_qa_longrun.py`

- round-trip determinístico com 10, 25 e 50 páginas;
- 20 objetos por página nos casos de escala;
- 20 ciclos consecutivos de save/load em documento de 25 páginas;
- 100 ciclos de move -> undo -> redo -> undo, exigindo retorno exato à geometria inicial;
- `assert_document_integrity()` em pontos críticos.

### `tools/g2_qa_baseline.py`

Coleta JSON sem transformar números de benchmark em requisitos rígidos de produto. Mede:

- build de documento;
- save (3 repetições);
- load (3 repetições);
- render PNG (3 repetições, 96 dpi/1080 px);
- render PDF multipágina (2 repetições, 96 dpi);
- tamanho de projeto/PNG/PDF;
- warnings do renderer;
- RSS antes/depois quando `/proc/self/status` está disponível;
- 30 ciclos consecutivos de save/load com amostras de RSS para detectar tendência de crescimento.

O benchmark cria `QGuiApplication` explicitamente antes de usar o renderer Qt, evitando atribuir ao renderer a falha já conhecida do harness que chama Qt sem aplicação GUI.

## Matriz inicial dos fluxos

| Fluxo | Cobertura disponível | Estado nesta branch |
|---|---|---|
| A — criar/editar/save/reopen | E2E real + package/project actions | Pendente de execução CI |
| B — importar PPTX/editar imagem/exportar PNG | testes PPTX + E2E/export Qt | Pendente de execução CI |
| C — importar PPTX/editar/exportar PDF | PPTX + PDF multipágina | Pendente de execução CI |
| D — ProductCards/bindings/save/reopen | E2E real + ProductCard tests | Pendente de execução CI |
| E — duplicate page/independência | clone IDs + E2E real | Pendente de execução CI |
| F — autosave/interrupção/recovery | autosave + E2E real | Pendente de execução CI |
| G — undo/redo/move/resize/delete/duplicate/save | E2E real + novo loop de 100 ciclos | Pendente de execução CI |

## Classificação atual

Nenhum novo P0/P1 deve ser declarado sem execução. Este relatório será atualizado com reprodução, duração, PASS/FAIL, métricas e dono sugerido a partir das evidências do workflow da branch.

## Comandos do gate Chat 5

```bash
python -m compileall -q src/srstudio/graphics2 tools/g2_qa_baseline.py tests/test_graphics2_qa_longrun.py
python -m ruff check tools/g2_qa_baseline.py tests/test_graphics2_qa_longrun.py
pytest -q \
  tests/test_graphics2_autosave.py \
  tests/test_graphics2_bridge_roundtrip.py \
  tests/test_graphics2_package_stress.py \
  tests/test_graphics2_page_clone_ids.py \
  tests/test_graphics2_project_actions.py \
  tests/test_graphics2_product_card_duplicate.py \
  tests/test_graphics2_pdf_multipage.py \
  tests/test_graphics2_real_flyer_e2e.py \
  tests/test_graphics2_qa_longrun.py
python tools/g2_qa_baseline.py --output artifacts/g2-qa-baseline.json --pages 1,10,25
pytest -q tests -k graphics2
```

## Resultados

A preencher exclusivamente com saídas observadas de CI/benchmark; não inferir PASS por existência de teste.
