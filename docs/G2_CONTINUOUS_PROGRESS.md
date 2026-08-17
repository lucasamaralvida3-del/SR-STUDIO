# SR Graphics Engine 2 — Continuous Progress

> Escopo absoluto: **somente o novo Studio de Encartes / SR Graphics Engine 2**.
> Este documento não autoriza alterações em Cartazes, Promoções, Atacado, Stable, Beta operacional, launcher, updater ou installer.

## Estado atual

- Branch de trabalho: `chatgpt/g2-professional-usable`
- Base usada: `integration/sr-studio-next` em `2456fc2cbf62c7a35e4f86cd968225809b7e4e37` (`graphics2: add canonical color pipeline`)
- Meta: `G2 PROFESSIONAL USABLE`, depois `G2 PRODUCTION CANDIDATE`
- Regra: preservar Golden Masters/thresholds oficiais; diagnósticos de usabilidade e content fidelity são complementares, nunca substitutos do gate oficial.
- Validação disponível nesta sessão: inspeção estática do repositório via GitHub. O ambiente desta sessão não executa o checkout completo/Qt/pytest do projeto, portanto os testes adicionados ainda precisam ser executados em ambiente local/Codex/CI antes de integração.

## Auditoria inicial

O G2 atual já possui SR Scene 2, Command Router, Qt/QML, edição geométrica, SmartSlots, binding de produtos, semântica de ProductCard/PriceBlock, importação PPTX/Canva, `.srscene`, preflight/Production Gate, Golden Masters, exportadores e ferramentas de layout.

### P1 encontrado — duplicação insegura de página

A implementação histórica de duplicação baseada em `deepcopy` alterava o `page.id`, mas podia preservar ids de nodes e SmartSlots. Como ids são referências canônicas, páginas duplicadas podiam compartilhar identidades e tornar seleção, semântica, merge/salvamento e comandos ambíguos.

Correção criada com clone independente e verificação estrutural.

## Ciclos concluídos nesta branch

### Ciclo 1 — identidade multipágina segura

**Problema:** duplicação de página podia reutilizar ids internos.

**Mudança:** `src/srstudio/graphics2/page_clone.py`

- regenera id da página;
- regenera ids de nodes;
- regenera ids de SmartSlots;
- remapeia roots/parent/children;
- remapeia bindings dos slots;
- remove ids semânticos obsoletos;
- reconstrói semantic blocks isoladamente;
- preserva assets compartilhados e snapshots de produto;
- fornece duplicação transacional/undoable.

Commits:
- `a441e426f98a5caf997fc98f67bce34f8cba8148` — `graphics2: add safe independent flyer page cloning`
- `f1ed7d1c1425c5c871c1e164eb9c4581a3350dd4` — `test: cover independent G2 page duplication`

### Ciclo 2 — gate estrutural de usabilidade

**Mudança:** `src/srstudio/graphics2/usability_gate.py`

O gate é separado do Golden Master visual e verifica:

- ids de páginas/nodes/slots;
- dimensões;
- roots;
- integridade parent/child;
- SmartSlot -> page;
- SmartSlot -> node bindings;
- semantic block members;
- conteúdo visível;
- texto editável;
- imagens;
- contagem de SmartSlots/bindings/ProductCards/PriceBlocks;
- requisito opcional de página multiproduto.

Commits:
- `7b7150069456c8cda14b50a469e42902ccdfc83d` — `graphics2: add professional flyer usability gate`
- `7b3dd58753605e90853d3d0d9e24b09d31416a42` — `test: add G2 professional usability gate coverage`
- `afc7ba539614362174b69db6f1ad1f070cc99dbd` — `tools: add G2 flyer usability checker`

CLI adicionada: `tools/g2_usability_check.py`.

### Ciclo 3 — smoke do fluxo principal

Teste de domínio criado para:

produto -> SmartSlot -> binding -> edição geométrica -> undo/redo -> duplicação segura -> save `.srscene` -> reopen -> gate estrutural.

Commit:
- `7ead8a0388fd4e55474507b805e52f4ee3a837f7` — `test: add end-to-end G2 flyer core workflow`

### Ciclo 4 — gerenciamento multipágina

**Mudança:** `src/srstudio/graphics2/page_management.py`

Serviços transacionais:

- renomear página;
- excluir página sem permitir documento com zero páginas;
- duplicar página com fresh ids;
- reordenar página;
- integração com undo/redo pelo histórico do `GraphicsSession`.

Commits:
- `c0be357dd5924eb2cd5aee2ce71ff5230c93b549` — `graphics2: add transactional multipage management service`
- `23d366f97158282e2bf7b6e3065f83aabfb5bc2f` — `test: cover transactional G2 multipage management`

### Ciclo 5 — substituição manual de imagem

**Mudança:** `src/srstudio/graphics2/asset_edit.py`

- troca fonte de image/background;
- reutiliza/cria AssetRef;
- preserva geometria;
- preserva crop/focus/zoom/flip por padrão;
- reset de framing apenas quando explícito;
- operação undoable;
- recusa node bloqueado ou não-imagem.

Commits:
- `82639da92a779009bedd9f537ebbfcb8a0c8678b` — `graphics2: add undoable manual image replacement service`
- `72ab588f0619892942c317b3ae6f96908e3a59ee` — `test: cover G2 manual image replacement`

### Ciclo 6 — edição profissional de texto

**Mudança:** `src/srstudio/graphics2/text_edit.py`

Edição atômica/undoable de:

- font family;
- font size;
- weight;
- italic;
- color;
- horizontal/vertical alignment;
- letter spacing;
- line spacing;
- opacity.

A geometria do template permanece intacta.

Commits:
- `11be3703391442c7990389ec803cd9d3a01f0686` — `graphics2: add undoable professional text style editing`
- `dc4818dc8ad4e6465b2b1871c77d44fdbd458606` — `test: cover G2 professional text style editing`

### Ciclo 7 — edição semântica de PriceBlock

**Mudança:** `src/srstudio/graphics2/price_edit.py`

- preço tratado como componente semântico, não caixas desconectadas;
- atualiza currency/reais/cents/complete/unit em uma transação;
- aceita formato BR/decimal;
- preserva geometria/style;
- mantém `product_snapshot` coerente;
- undo restaura bloco inteiro.

Commits:
- `84e8e29c460680fe8d81aee7db368b796dbc0c50` — `graphics2: add atomic semantic PriceBlock editing`
- `8cc4fc6bad3fbe0df2f30778ed0323923c796622` — `test: cover atomic G2 PriceBlock editing`

### Ciclo 8 — edição atômica de ProductCard

**Mudança:** `src/srstudio/graphics2/product_card_edit.py`

Uma operação pode editar, sem desmontar o design:

- nome;
- preço;
- unidade;
- imagem;
- limite;
- preço app.

Usa bindings primários + `extra_bindings`, mantém `product_snapshot`, preserva geometria/framing e integra com undo/redo.

Commits:
- `49d3c856353e609954bad332312309375d23f73c` — `graphics2: add atomic ProductCard field editing`
- `f3f47f8db4824088313c4b2d64a10b33fc32afc3` — `test: cover atomic G2 ProductCard editing`

### Ciclo 9 — autosave/recovery endurecido

O G2 já possuía `AutosaveManager`; ele foi preservado e ampliado de forma retrocompatível.

**Mudança:** `src/srstudio/graphics2/autosave.py`

- fingerprint determinístico da SR Scene;
- `save_if_changed` para evitar autosaves redundantes;
- cadence control sem thread oculta;
- `mark_current_state` após save manual;
- geração explícita continua disponível em `save`;
- recovery points inválidos não escondem gerações anteriores válidas;
- detecção de recovery mais novo que projeto manual;
- limpeza limitada somente aos autosaves do documento;
- autosave nunca sobrescreve o `.srscene` manual.

Commits:
- `e779b12645ffea5300a0bb196f6313dbb0fa9794` — `graphics2: harden autosave dirty detection and recovery`
- `7f216dacc296b7f4ac1f97a41dde9256cd384099` — `test: cover hardened G2 autosave and recovery`

## Funcionalidades existentes auditadas e preservadas

- Command Router para move/resize/rotate/selection/layers/group/undo/redo/bind product;
- Smart Layout e fill de slots;
- PPTX/Canva import bridge;
- semântica de ProductCard/PriceBlock;
- QML do editor, painel de páginas/produtos/layers;
- ImageInspector com contain/cover/fill, crop, zoom, focus e flip;
- pacote `.srscene` com save/load e integridade;
- preflight/Production Gate;
- exportadores existentes.

## Ainda NÃO integrado na UI/Command Router

Os serviços novos foram mantidos isolados deliberadamente para reduzir risco enquanto não há execução completa de pytest/Qt nesta sessão. Precisam de wiring controlado:

- `page_clone.py` / `page_management.py` substituir fluxo antigo de duplicate page;
- `asset_edit.py` conectar a ação “Substituir imagem” do inspector;
- `text_edit.py` conectar ao painel de propriedades de texto;
- `price_edit.py` conectar a seleção/edição de PriceBlock;
- `product_card_edit.py` conectar ao painel semântico de ProductCard;
- `autosave.save_if_changed` conectar ao timer/event loop já existente do host, sem thread oculta;
- `usability_gate.py` conectar a diagnóstico/preflight de Preview, sem alterar Production Gate visual.

## Gates de validação antes de merge

Executar no ambiente completo:

1. suíte `tests/test_graphics2_*.py`;
2. suíte completa SR Studio para confirmar zero regressão fora de G2;
3. Qt host smoke;
4. importar corpus PPTX real;
5. abrir página completa;
6. selecionar/mover/resize;
7. editar ProductCard/PriceBlock;
8. substituir imagem;
9. undo/redo;
10. duplicar/reordenar/excluir página;
11. salvar/reabrir `.srscene`;
12. autosave/recovery;
13. PNG;
14. PDF;
15. preview/export parity;
16. Golden Masters oficiais sem alteração de thresholds;
17. content-aware fidelity diagnostics;
18. teste real de encarte multiproduto.

## Próximas prioridades

P1/P2 imediatas:

1. executar e corrigir testes desta branch em ambiente completo;
2. wiring seguro dos serviços novos no Command Router/Qt host/QML;
3. garantir que duplicate page use exclusivamente fresh ids;
4. expor edição semântica de ProductCard e PriceBlock na UI;
5. expor Replace Image preservando framing;
6. integrar autosave timer/recovery prompt;
7. finalizar fluxo multipágina (rename/delete/reorder/duplicate no UI);
8. validar PNG/PDF e preview parity;
9. medir content fidelity em encarte real;
10. atacar P1 visual de line-box/anchor/WordArt/transforms somente com métricas.

## Regra de handoff

Quando Codex voltar, **não reiniciar o projeto e não refazer estas implementações do zero**. Fazer checkout/fetch desta branch, executar testes, corrigir o que falhar e integrar incrementalmente. Nenhum trabalho desta branch autoriza alteração dos módulos proibidos.
