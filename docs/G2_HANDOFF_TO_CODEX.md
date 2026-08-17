# SR Graphics Engine 2 — Handoff para Codex

Data: 2026-08-17

## Missão permanente

Continuar **somente** o novo Studio de Encartes / SR Graphics Engine 2 até:

1. `G2 PROFESSIONAL USABLE`;
2. depois `G2 PRODUCTION CANDIDATE`.

Não trabalhar por iniciativa em Cartazes, Promoções, Atacado, Stable, Beta operacional, launcher, updater, installer ou demais módulos do SR Studio.

## Ponto exato de retomada

- Repositório: `lucasamaralvida3-del/SR-STUDIO`
- Branch: `chatgpt/g2-professional-usable`
- PR de validação: `#25` — **DRAFT / NÃO MESCLAR AINDA**
- Base: `integration/sr-studio-next`
- Base SHA usada: `2456f320b22834c041b69badf7e020ae83138738`
- Head validado em Linux: `5848789d709d78bf229695ed43a46db27a9a808b`

Ao retomar:

```text
git fetch origin
git switch chatgpt/g2-professional-usable
git pull --ff-only
```

Não resetar para `integration/sr-studio-next` e não reimplementar os ciclos abaixo do zero.

## Validação CI no head 5848789

### Linux / core-and-regression — PASS

Passou:

- compile Python;
- Ruff;
- Visual Fidelity and Production Gate;
- Fidelity Lab CLI;
- Fidelity Triage CLI;
- Golden Master CLI;
- Reference Suite CLI;
- PPTX Structure CLI;
- PPTX Effects CLI;
- Graphics Host CLI;
- Graphics Engine 2 tests;
- Full SR Studio regression suite.

Resultados:

- suite de fidelidade/gate focada: `136 passed, 3 skipped`;
- Graphics2: `351 passed, 18 skipped, 223 deselected`;
- regressão completa SR Studio: `574 passed, 18 skipped`;
- zero failures.

Warnings conhecidos:

- dois warnings novos de depreciação Pillow em `graphics2/content_fidelity.py` (`getdata`);
- warnings históricos de `src/srstudio/images/library.py` permanecem fora do escopo desta branch.

### Windows / Qt Quick

No momento da criação deste handoff, o job Windows do mesmo head estava instalando dependências GPU. Verificar o estado do PR #25 antes de qualquer nova integração visual.

## Implementações concluídas

### 1. Duplicação de página segura

`src/srstudio/graphics2/page_clone.py`

- fresh page id;
- fresh node ids;
- fresh SmartSlot ids;
- remapeamento root/parent/children/bindings;
- semantic blocks reconstruídos;
- assets e snapshots preservados.

Corrige o risco histórico de `deepcopy` reutilizar ids entre páginas.

### 2. Gerenciamento multipágina transacional

`src/srstudio/graphics2/page_management.py`

- duplicate;
- rename;
- delete;
- reorder;
- undo/redo;
- nunca deixa documento sem página.

### 3. Gate estrutural de usabilidade

`src/srstudio/graphics2/usability_gate.py`

Valida:

- ids;
- roots;
- parent/child;
- slot -> page;
- slot -> node;
- semantic members;
- conteúdo visível;
- texto editável;
- imagens;
- ProductCards;
- PriceBlocks;
- multiproduto opcional.

CLI: `tools/g2_usability_check.py`.

Esse gate NÃO substitui Golden Master/Production Gate visual.

### 4. Reparo de projetos antigos com ids colididos

`src/srstudio/graphics2/identity_repair.py`

- detecta colisões de page/node/slot;
- mantém a primeira ocorrência canônica;
- reidentifica somente páginas posteriores colididas;
- preserva layout/assets;
- undoable.

### 5. ProductCard editável como unidade semântica

`src/srstudio/graphics2/product_card_edit.py`

Uma única operação pode alterar:

- nome;
- preço;
- unidade;
- imagem;
- limite;
- preço App.

Mantém bindings/snapshot e não desmonta o design.

### 6. PriceBlock semântico

`src/srstudio/graphics2/price_edit.py`

Edita junto:

- R$;
- reais;
- centavos;
- unidade;
- preço completo quando presente.

Preserva geometria/style e mantém snapshot coerente.

### 7. Substituição de imagem

`src/srstudio/graphics2/asset_edit.py`

- preserva size/crop/focus/zoom/flip por padrão;
- reset de framing explícito;
- undoable;
- não altera imagem bloqueada.

### 8. Edição profissional de texto

`src/srstudio/graphics2/text_edit.py`

- font family;
- size;
- weight;
- italic;
- color;
- align;
- vertical align;
- letter spacing;
- line spacing;
- opacity;
- undoable.

### 9. Autosave/recovery endurecido

`src/srstudio/graphics2/autosave.py`

- fingerprint da SR Scene;
- `save_if_changed`;
- cadence control;
- `mark_current_state`;
- gerações;
- recuperação ignora geração corrompida sem esconder anterior válida;
- autosave nunca sobrescreve `.srscene` manual;
- `BadZipFile` tratado.

### 10. Planejamento conservador de preenchimento multiproduto

`src/srstudio/graphics2/slot_fill_plan.py`

Fluxo:

`lista explícita de produtos -> plano -> revisão -> aplicação`

Pula por padrão:

- slot bloqueado;
- baixa confiança;
- slot já preenchido.

A aplicação rejeita plano stale se slot/produto mudou após o planejamento.

### 11. Painel de propriedades contextual

`src/srstudio/graphics2/inspector_context.py`

Contextos separados:

- página;
- texto;
- imagem;
- ProductCard;
- PriceBlock;
- shape;
- group;
- multisseleção.

Evita mostrar dezenas de propriedades irrelevantes.

### 12. Estado profissional read-only

`src/srstudio/graphics2/professional_state.py`

Expõe para UI:

- inspector atual;
- capabilities da página;
- usabilidade;
- semantic selection;
- preferência pelo PriceBlock mais estreito quando seleção é somente preço.

### 13. Professional Command Router

`src/srstudio/graphics2/professional_command_router.py`

Retrocompatível com o router histórico e adiciona/intercepta:

- safe `duplicate_page`;
- rename/delete/reorder page;
- replace image;
- edit text style;
- edit PriceBlock;
- edit ProductCard;
- inspect usability;
- repair legacy identities;
- plan/apply slot fill;
- inspect properties.

`payload()` adiciona `editor.professional` sem remover os campos históricos.

`dispatch_json()` preserva `payload = cena` e acrescenta `command_payload` para respostas específicas, mantendo QML legado compatível.

### 14. Host Qt profissional opt-in

`src/srstudio/graphics2/professional_qt_host.py`

O `qt_host.py` estável NÃO foi alterado.

O host opt-in:

- injeta `ProfessionalGraphicsCommandRouter` temporariamente;
- anexa `ProfessionalInspector.qml`;
- restaura hooks ao sair.

Isso permite validar o modo PRO antes da troca definitiva do host.

Executável de teste:

```text
python -m srstudio.graphics2.professional_qt_host <arquivo.pptx-ou-srscene>
```

### 15. Professional Inspector QML

`src/srstudio/graphics2/qml/ProfessionalInspector.qml`

Painel contextual opt-in com:

- rename/duplicate/delete/reorder página;
- texto + font size/family/color;
- substituir imagem preservando framing;
- ProductCard: nome/preço/unidade/limite/preço App/imagem;
- PriceBlock: preço/unidade;
- multiselection align/distribute;
- preparar/aplicar SmartSlot fill;
- reparar IDs antigos quando gate detecta bloqueios;
- indicação de blockers estruturais.

Há smoke QML real em `tests/test_graphics2_professional_qml.py` para rodar quando PySide6 estiver disponível.

### 16. Export contract imutável

`src/srstudio/graphics2/export_contract.py`

- export trabalha sobre snapshot canônico;
- fingerprint live-scene antes/depois;
- exportador pode alterar snapshot temporário;
- projeto aberto não pode ser alterado silenciosamente.

### 17. Content-aware fidelity

`src/srstudio/graphics2/content_fidelity.py`

Diagnósticos complementares:

- bbox ref/render;
- IoU;
- delta X/Y;
- width/height error;
- center distance;
- foreground pass;
- foreground changed area;
- mask IoU;
- ink coverage;
- content score diagnóstico.

Página vazia diante de referência com conteúdo é penalizada, mesmo se o fundo branco gerar score global enganoso.

### 18. Agregados nomeados

`src/srstudio/graphics2/content_fidelity_report.py`

Expõe:

- `CONTENT_REGION_SCORE`;
- `TEXT_REGION_SCORE`;
- `WORDART_REGION_SCORE`;
- `IMAGE_REGION_SCORE`;
- `SHAPE_REGION_SCORE`;
- `FOREGROUND_PIXEL_PASS`;
- `FOREGROUND_CHANGED_AREA`;
- `MASK_IOU`;
- `BBOX_IOU`.

Sempre marca:

- `diagnostic_only = true`;
- `official_gate_unchanged = true`.

### 19. Content attribution scene-aware

`src/srstudio/graphics2/content_attribution.py`

Combina Attribution Lab com métricas content-aware e classifica regiões em:

- TEXT;
- WORDART;
- IMAGE;
- SHAPE;
- OTHER.

Relata métricas ausentes/orphans explicitamente.

## Golden Masters e fidelity policy

NÃO alterar:

- referência oficial;
- thresholds;
- score mínimo;
- pixel-pass mínimo;
- changed-area máximo.

Content-aware é diagnóstico paralelo.

Motivo: baseline quase vazio pode receber score global alto por coincidir com grandes áreas brancas. Priorizar sobreposição real de conteúdo.

## Próximos P1/P2

Executar na ordem:

1. confirmar Windows CI do head atual;
2. se `ProfessionalInspector.qml` falhar no smoke Qt, corrigir sem tocar `GraphicsEditor.qml` estável;
3. abrir encarte real pelo `professional_qt_host`;
4. validar seleção contextual;
5. validar ProductCard/PriceBlock em UI;
6. validar Replace Image em UI;
7. validar page duplicate/rename/delete/reorder em UI;
8. integrar autosave timer/recovery prompt no host opt-in;
9. integrar `run_snapshot_export` ao caminho opt-in de PNG/PDF;
10. medir preview/export parity;
11. medir content-aware no corpus real;
12. atacar fidelity P1: DrawingML transforms/off-slide -> Office line-box -> vertical anchor -> transformed margins -> baseline/height -> WordArt;
13. nunca usar offsets específicos de template.

## Teste real obrigatório antes de G2 PROFESSIONAL USABLE

1. abrir Studio de Encartes;
2. importar PPTX real;
3. página completa aparece;
4. selecionar produto;
5. alterar nome;
6. alterar preço;
7. trocar imagem;
8. mover;
9. resize;
10. undo;
11. redo;
12. duplicar página;
13. reordenar página;
14. salvar `.srscene`;
15. fechar;
16. reabrir;
17. validar persistência;
18. autosave/recovery;
19. export PNG;
20. export PDF;
21. abrir exports;
22. comparar preview/export;
23. rodar usability gate;
24. rodar Golden Master oficial;
25. rodar content-aware paralelo.

## Condição de handoff

Codex deve começar lendo:

- `AGENTS.md`;
- `docs/SR_STUDIO_NEXT_ARCHITECTURE.md`;
- `docs/G2_CONTINUOUS_PROGRESS.md`;
- este arquivo.

Depois verificar PR #25 e CI.

**Não perguntar “posso continuar?”**. Prosseguir por ciclos P0 -> P1 -> P2 até G2 PROFESSIONAL USABLE/PRODUCTION CANDIDATE ou bloqueio externo real.
