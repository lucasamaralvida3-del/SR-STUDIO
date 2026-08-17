# G2 Continuous Progress — SR Studio de Encartes

Atualizado: 2026-08-17

## Estado

- **Branch de trabalho:** `integration/sr-studio-next`
- **Alpha:** `0.43.0-alpha` / Alpha 43
- **Último commit G2 confirmado verde em CI:** `b583b6760ab3ed4a1e2cdafb553b0ef6378d3bbf`
- **Head documentado deste ciclo:** `2b621ef179339c6e0ed53a3109de87454b4706db`
- **G2_USABILITY_SCORE atual:** **90/100 provisório, com soma formal abaixo**
- **P0 conhecidos:** 0 no último estado verde
- **P1 atual:** fechar E2E multiproduto/2 páginas e validar o batch pós-`b583b676`; corpus Golden Master oficial atual ainda não foi reexecutado neste ciclo
- **P2 atual:** medição fresca de performance e fidelidade oficial do corpus

> Regra: o score só sobe com evidência. Commits posteriores ao último verde não são promovidos a `LAST_SAFE_COMMIT` até a CI G2 Ubuntu + Windows/Qt Quick concluir com sucesso.

## Recovery Audit desta sessão

O Recovery Audit foi iniciado antes de qualquer alteração.

- `AGENTS.md` lido.
- `docs/SR_STUDIO_NEXT_ARCHITECTURE.md` lido.
- `docs/G2_CONTINUOUS_PROGRESS.md` e `docs/G2_USABLE_PREVIEW.md` não existiam no HEAD remoto inicial desta sessão.
- HEAD remoto inicial observado: `2456f320b22834c041b69badf7e020ae83138738`.
- O último commit G2 anterior comprovado verde era `c10ca92428351facbe1491009004f113621ab95c` (Alpha 43).
- A comparação `c10ca924..2456f320` mostrou que os commits posteriores não alteravam `src/srstudio/graphics2`.
- A branch histórica `feature/sr-graphics-engine-2` estava atrasada (Alpha 28) e não foi usada como base.
- O estado local do computador do usuário (`git status`, commits locais e mudanças não commitadas locais) não é observável nesta execução remota; nada local foi apagado ou resetado.
- `main` e `stable` não foram alteradas.

## CI comprovada

### `b583b6760ab3ed4a1e2cdafb553b0ef6378d3bbf`

Run G2 confirmado verde:

- Ubuntu `core-and-regression`: PASS
  - compile
  - Ruff
  - Visual Fidelity / Production Gate tests
  - CLI smoke
  - testes `graphics2`
  - regressão completa
- Windows `qt-quick-host`: PASS
  - Qt Quick runtime real
  - backend probe
  - Visual Fidelity tests
  - testes G2
- PDF multipágina real: PASS no teste adicionado até esse commit.

## Correções já promovidas a estado verde

### ProductCard / PriceBlock / SmartSlot

- Duplicação de ProductCard deixou de clonar apenas pixels/nós.
- O clone recebe novos IDs de nós, SmartSlot e blocos semânticos.
- Bindings são remapeados e isolados entre original e cópia.
- Undo/redo da duplicação é atômico.
- Copy/paste semântico foi adicionado ao router.
- Copy/paste entre páginas preserva ProductCard, PriceBlock e SmartSlot, com IDs novos.
- Ctrl+C / Ctrl+V e botões visíveis foram adicionados ao Qt/QML.
- Excluir ProductCard agora poda SmartSlots e SemanticBlocks órfãos.

### Multipágina

- `delete_page` transacional implementado.
- A última página não pode ser apagada.
- Ao excluir a página ativa, uma vizinha segura passa a ser ativa.
- Undo/redo funciona.
- `PageInspector.qml` expõe adicionar, duplicar, reordenar e excluir página.
- PDF multipágina é aberto pelo teste com `pypdf` e validado como arquivo de duas páginas reais.

### Persistência / autosave / recovery

- Autosave integrado ao host Qt, não apenas ao gerenciador unitário.
- Debounce de 1,5 s após mutações.
- Snapshot antes de IO.
- Gravação em thread separada da UI.
- Assets locais configurados para inclusão no autosave.
- Flush final no fechamento do aplicativo.
- Recovery explícito, sem sobrescrever silenciosamente o projeto ao abrir.
- Recovery substitui documento, limpa seleção e histórico antigo.
- Botão `Recuperar` exposto na UI.

## Batch atual aguardando promoção a LAST_SAFE_COMMIT

### Duplicação de página sem colisão

Commits principais:

- `5af216dd1b43f51eed88936cd030232e6a5601ed` — utilitário de clone de página com IDs novos.
- `68fe542e27eb2f70d7606afad8fad5ad62cb03dd` — `GraphicsSession.add_page(duplicate_active=True)` usa clone com remapeamento completo.
- `b2babd66e1a1810f7810f228f88d217ab464f811` — testes de unicidade de página/nós/slots/blocos e undo/redo.
- `606a47f9db5262fb2e6d088fd1d3742888739f13` — preflight passa a rejeitar IDs internos repetidos entre páginas.
- `692479e16f065a70c2015040f299184abbb607cd` — teste de regressão do preflight global.

Causa raiz corrigida: a duplicação anterior fazia `deepcopy` da página e mudava apenas `page.id`; nós, SmartSlots e SemanticBlocks mantinham IDs iguais em páginas diferentes.

### E2E principal de produto

Commit:

- `d74271f5bbbdd968978ebc245c3f946bb31e8655` — teste E2E de encarte com 10 ProductCards e 2 páginas.

O E2E cobre:

1. 10 produtos;
2. preenchimento semântico;
3. substituição de 3 produtos;
4. troca efetiva de imagens via binding;
5. edição de 3 nomes;
6. edição de 3 preços;
7. mover cards;
8. resize de card com escala dos filhos;
9. duplicar card;
10. excluir card;
11. undo;
12. redo;
13. z-order;
14. duplicar segunda página;
15. modificar segunda página;
16. unicidade global dos IDs;
17. save `.srscene` com assets;
18. reopen;
19. preservação das edições;
20. autosave;
21. recovery;
22. PNG real;
23. PDF real multipágina;
24. abertura dos exports para validação estrutural.

## Score provisório — 90/100

Pontuação conservadora; nenhum bloco recebe crédito por intenção. O score não será aumentado enquanto o batch E2E atual não estiver verde.

| Bloco | Pontos | Evidência atual |
|---|---:|---|
| A. Estabilidade | 14/15 | CI Ubuntu/Windows verde até `b583b676`; save/export/host real; hardening de stress final ainda pendente |
| B. Editor visual | 20/20 | select/multi/move/resize/aspect/rotate/delete/duplicate/copy/paste/undo/redo/layers/zoom/pan/fit/snap/propriedades e feedback básico presentes |
| C. ProductCards/PriceBlocks | 15/15 | ProductCard/PriceBlock/SmartSlot, imagem/nome/preço/unidade/limite/app, substituição preservando design, bindings e undo/redo cobertos pelo código/testes; corpus ainda influencia D/I, não este contrato funcional |
| D. Importação PPTX/Canva | 7/10 | pipeline e testes existentes; matriz atual do corpus real ainda pendente |
| E. Multipágina | 9/10 | add/duplicate/delete/select/reorder/save/PDF presentes; promoção do fix de IDs aguarda CI |
| F. Persistência/autosave | 9/10 | round-trip existente + autosave/recovery integrados; restart/stress final pendente |
| G. Exportação | 8/8 | PNG/PDF e PDF multipágina real cobertos |
| H. Performance | 4/5 | histórico adequado; nova medição deste ciclo pendente |
| I. Fidelidade | 2/5 | pipeline e testes de fidelidade existem, mas Golden Masters oficiais atuais ainda não foram medidos neste ciclo |
| J. UX/acabamento | 2/2 | status/busy/tooltips/atalhos/ações essenciais presentes |

**Cálculo:** 14 + 20 + 15 + 7 + 9 + 9 + 8 + 4 + 2 + 2 = **90/100**.

## Próximas ações exatas

1. Obter conclusão da CI G2 do HEAD mais recente; se falhar, corrigir antes de promover.
2. Validar o E2E `test_graphics2_real_flyer_e2e.py` em Ubuntu e Windows/Qt real.
3. Corrigir qualquer P0/P1 revelado pelo E2E.
4. Auditar corpus PPTX real disponível e gerar matriz PASS/PARTIAL/FAIL por IMPORT/GRAPHICS/TEXT/IMAGE/CROP/GROUP/SHAPE/PRICE/PRODUCTCARD/SMARTSLOT/BINDINGS/SAVE-OPEN/PNG/PDF.
5. Recalcular `G2_USABILITY_SCORE` com evidência por item.
6. Medir performance fresca somente após zero P1 de fluxo.
7. Rodar Golden Masters oficiais sem alterar thresholds/baselines.
8. Ao chegar a >=95, executar corpus inteiro + E2E + host Qt/QML + persistence/recovery/export/performance.
9. Ao chegar a >=98, executar 98% HARDENING antes de declarar practically ready.
