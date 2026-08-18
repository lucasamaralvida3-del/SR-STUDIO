# CHAT 4 — ProductCards + PriceBlocks + Smart Slots + Bindings

## Identificação e isolamento

- Repositório: `lucasamaralvida3-del/SR-STUDIO`
- Linha G2 usada como base: `g2/chatgpt-professional-usable`
- `BASE_SHA`: `89c91da05922d080453dcf42489dc671091bf671`
- Branch exclusiva: `g2/parallel-product-system`
- Estado da branch imediatamente antes deste relatório: `37` commits à frente e `0` atrás do `BASE_SHA`.
- `main` e `stable`: não alterados por este CHAT 4.
- Nenhuma branch paralela foi mesclada.
- Nenhum reset/clean destrutivo foi usado.

### Limitação do ambiente desta sessão

O checkout local do SR-STUDIO não estava montado no container desta sessão e o container não conseguia resolver `github.com`. Portanto não foi possível criar fisicamente o worktree solicitado em `../SR-STUDIO-g2-product-system`, nem executar `git status`/`pytest` localmente. O isolamento foi mantido pelo conector GitHub: a branch `g2/parallel-product-system` foi criada exatamente no `BASE_SHA` e todas as escritas foram feitas somente nela.

Também não foi possível observar um run de push do GitHub Actions pelo conector disponível nesta sessão. Consequentemente, os testes abaixo foram criados e adicionados ao gate CI, mas este relatório **não afirma que eles passaram em execução real**. A integração deve executar o workflow `G2 Product System` ou os comandos equivalentes em um checkout normal antes do merge.

## Objetivo entregue

Foi criada uma camada de produção inteligente G2 capaz de representar e atualizar ProductCards, PriceBlocks e SmartSlots sem acoplar a lógica ao QML. O fluxo de backend agora suporta:

1. criar um ProductCard inteligente;
2. vincular ou substituir um produto;
3. atualizar nome, descrição, imagem, preço normal/varejo, preço App/Clube, preço atacado, quantidade, unidade, limite e validade quando existentes no slot;
4. preservar a geometria dos elementos durante a troca de dados;
5. limpar campos opcionais e imagem antiga quando o produto substituto não possui esses dados;
6. atualizar apenas um card ou atualizar o produto compartilhado em cascata em todas as páginas;
7. detectar referências órfãs no preflight;
8. remover um SmartSlot mantendo os visuais sem permitir que a recuperação semântica recrie automaticamente o slot removido;
9. religar explicitamente nodes previamente desvinculados;
10. duplicar páginas com ProductCards mantendo IDs independentes e referências remapeadas.

## Arquivos alterados

### Runtime G2

- `src/srstudio/graphics2/__init__.py`
- `src/srstudio/graphics2/binding_runtime.py`
- `src/srstudio/graphics2/commercial_price_runtime.py`
- `src/srstudio/graphics2/preflight.py`
- `src/srstudio/graphics2/product_card_runtime.py`
- `src/srstudio/graphics2/product_data_runtime.py`
- `src/srstudio/graphics2/semantic_named_slot_runtime.py`
- `src/srstudio/graphics2/semantic_runtime.py`

### Testes CHAT 4

- `tests/test_graphics2_binding_integrity.py`
- `tests/test_graphics2_canonical_commercial_priceblocks.py`
- `tests/test_graphics2_complete_price_recovery.py`
- `tests/test_graphics2_core.py`
- `tests/test_graphics2_named_slot_v2_migration.py`
- `tests/test_graphics2_product_card_creation.py`
- `tests/test_graphics2_product_command_compat.py`
- `tests/test_graphics2_product_data_cascade.py`
- `tests/test_graphics2_product_page_duplicate.py`
- `tests/test_graphics2_product_system.py`
- `tests/test_graphics2_slot_detach.py`
- `tests/test_graphics2_wholesale_price_slot.py`

### Gate isolado

- `.github/workflows/g2-product-system.yml`

### Documentação

- `docs/parallel/CHAT4_PRODUCT_SYSTEM.md`

## Commits

A implementação foi feita em commits pequenos por ciclo. Antes da criação deste relatório, a branch possuía 37 commits sobre o `BASE_SHA`. Entre os commits confirmados durante a sessão estão:

- `629976118769...` — `fix(g2): unify product binding runtime`
- `486fc8a5a8cf...` — testes de binding comercial e isolamento
- `d7052f264058...` — regressão de preço completo recuperado
- `f08442e041bc...` — estados/round-trip/duplicação de ProductCard
- `1fd3966640c5...` — gate CI inicial do product system
- `184a56313928...` — recuperação de Atacado/Quantidade em slots nomeados
- `f7596c495e67...` — runtime de PriceBlock comercial
- `bce912255479...` — integração dos PriceBlocks comerciais ao rebuild
- `f0a5fbbf0faf...` — testes Varejo/Atacado/Quantidade
- `ba382eb072b5...` — preflight de bindings órfãos
- `f076b5267284...` — testes de integridade de binding
- `4e471ce724d4...` — preservação do ID estável `named-slot-v2`
- `8ca58936bee7...` — migração em-place de SmartSlot nomeado v2
- `b4162f2fdee9...` — testes de migração v2→v3
- `c539ec12b86f...` — criação de ProductCard e comandos de backend
- `63fbec02977a...` — comandos ProductCard transacionais/seguros
- `e98b1b69efc4...` — ativação da API ProductCard no pacote G2
- `12ea4dfe62af...` — testes end-to-end de criação/edição/troca
- `5756675f7a49...` — remoção de acesso a campo inexistente do relatório semântico
- `d36dbde24738...` — ampliação do gate CHAT 4
- `f99177d384db...` — proteção de nodes detached na recuperação semântica
- `18eaf665b674...` — remoção persistente de SmartSlot

Os ciclos posteriores adicionaram, ainda na mesma branch e sem merge externo: testes de detach, atualização local/cascata de produto, compatibilidade `drop_product`, reativação por rebind, cascata de imagem, PriceBlocks canônicos Varejo/Atacado, duplicação completa de ProductCard e consolidação do workflow. O histórico completo e autoritativo é o intervalo:

`89c91da05922d080453dcf42489dc671091bf671..g2/parallel-product-system`

## Correções P0/P1/P2/P3

### P0

- Durante a revisão do próprio patch foi detectada uma tentativa de incrementar `SemanticBlockReport.protected_product_nodes`, campo que não existe. Isso teria quebrado `build_semantic_blocks()` para slots comerciais. Foi removido antes da integração (`5756675f7a49...`).
- Nenhum P0 conhecido permanece aberto nesta branch, porém a ausência de execução real do gate nesta sessão impede declarar P0=zero de forma definitiva.

### P1 corrigidos

1. **Preço recuperado podia sumir na troca de produto**
   - SmartSlot recuperado usava `retail_price`, mas o binder Canva não formatava esse papel.
   - `retail_price` e `price_complete` agora compartilham o contrato de preço completo.

2. **Imagem errada permanecia após substituir produto**
   - Se o novo produto não tinha imagem, a foto anterior podia permanecer.
   - Agora `asset_id` e `bound_image_source` são limpos e o node é ocultado.

3. **Campos opcionais antigos permaneciam**
   - App price, atacado, quantidade, limite, validade e descrição agora ficam vazios/ocultos quando ausentes no novo produto.

4. **Bindings extras podiam ficar órfãos**
   - `GraphicsPage.remove_node()` agora limpa `extra_bindings` e IDs auxiliares.
   - Preflight sinaliza node primário/extra inexistente e slot apontando para página errada.

5. **Varejo + Atacado + Quantidade não formavam um ProductCard comercial completo**
   - Marcadores nomeados `SR_PRECO_ATACADO`/`WHOLESALE` e `QUANTIDADE/QTD/MINIMO` são reconhecidos na camada semântica G2.
   - O ProductCard recebe PriceBlock principal e PriceBlock `commercial_role=wholesale`.

6. **API canônica e template importado tinham semântica diferente**
   - `BindingRole.RETAIL_PRICE` agora é tratado como preço completo principal.
   - `BindingRole.WHOLESALE_PRICE` também produz PriceBlock de Atacado.

7. **Migração de slot nomeado poderia trocar o ID**
   - A capacidade passou para metadata versão 3, mas o sal de identidade permanece `named-slot-v2` para compatibilidade com projetos salvos.

8. **Projeto v2 salvo não ganhava Atacado/Quantidade sem recriar slot**
   - Slots v2 são enriquecidos em-place preservando `slot.id`, `product_id`, `locked` e `product_snapshot`.

9. **Remover SmartSlot mantendo os visuais podia fazer o slot reaparecer**
   - Nodes recebem `smart_slot_detached=true` e ficam fora da recuperação automática durante rebuild, sem mudar sua visibilidade final.

10. **Rebind de nodes detached podia manter estado residual**
    - Binding explícito remove `smart_slot_detached`/`detached_from_slot_id` e reativa o contrato semântico.

11. **Atualização de dados não propagava entre páginas**
    - `update_product_data(product_id, changes, cascade=True)` atualiza catálogo e todos os slots desbloqueados com o mesmo produto em uma transação.
    - Slot bloqueado é preservado e reportado como `slots_skipped_locked`.

12. **Duplicação precisava manter referências independentes**
    - Os contratos agora cobrem `node_by_role`, `extra_bindings`, PriceBlocks, snapshots e IDs após duplicação de página.

13. **Wrappers novos podiam quebrar drag-and-drop legado**
    - O encadeamento mantém `drop_product → self.dispatch(bind_product)` funcional e preserva `drop_target` no payload.

### P2 / limitações conhecidas

- O modelo central `Product` não possui campo dedicado `description`. O G2 aceita `product["description"]` quando fornecido por chamada direta e, para persistência compatível com o modelo atual, usa `product.metadata["description"]` como formato recomendado.
- A UI/QML para expor botões/formulários dos novos comandos pertence ao CHAT 3.
- Nenhuma refatoração do serializer core foi feita; os dados novos usam estruturas já serializáveis (`metadata`, `node_by_role`, `extra_bindings`, `product_snapshot`).

### P3

- Textos/labels específicos de UI para Varejo/Atacado/App podem ser refinados no CHAT 3 sem alterar o contrato do backend.

## Contrato de ProductCard

### Comando de criação

```python
{
    "name": "create_product_card",
    "x": 100,
    "y": 100,
    "width": 420,
    "height": 360,
    "product_name": "Novo produto",
    "include_image": True,
    "include_description": True,
    "include_quantity": True,
    "include_validity": True,
    "include_app_price": True,
    "include_wholesale": True,
}
```

Retorna `slot_id`, `product_card_id`, `node_by_role` e `extra_bindings`.

### Binding de produto

```python
{
    "name": "bind_product",
    "slot_id": "slot-id",
    "product": {
        "id": "produto-1",
        "display_name": "CAFÉ 500G",
        "description": "TORRA MÉDIA",
        "price": "19,90",
        "retail_price": "19,90",
        "app_price": "17,49",
        "wholesale_price": "16,89",
        "quantity": "6",
        "unit": "UN",
        "cpf_limit": "12UN",
        "validity": "20/08/2026",
        "image_path": "cafe.png"
    }
}
```

### Edição local de um card

```python
{
    "name": "update_product_fields",
    "slot_id": "slot-id",
    "changes": {
        "display_name": "CAFÉ DESTAQUE 500G",
        "price": "18,99"
    }
}
```

Esse comando altera o snapshot/visual somente daquele card e não modifica o registro compartilhado em `document.metadata["products"]`.

### Atualização compartilhada em cascata

```python
{
    "name": "update_product_data",
    "product_id": "produto-1",
    "changes": {
        "price": "21,49",
        "quantity": "12",
        "image_path": "cafe-novo.png"
    },
    "cascade": True
}
```

Resultado inclui `slots_updated`, `slots_skipped_locked`, `catalog_updated` e `page_ids`.

### Rebind

```python
{
    "name": "rebind_slot",
    "slot_id": "slot-id",
    "bindings": {
        "name": "node-name",
        "retail_price": "node-retail"
    },
    "extra_bindings": {
        "app_price_complete": ["node-app"],
        "wholesale_price": ["node-wholesale"]
    }
}
```

Nodes inexistentes são rejeitados antes da mutação.

### Remoção

```python
{
    "name": "remove_smart_slot",
    "slot_id": "slot-id",
    "delete_nodes": False
}
```

Com `delete_nodes=False`, os visuais são preservados e marcados como detached para impedir recuperação automática. Com `delete_nodes=True`, os nodes ligados são removidos.

## PriceBlocks

Formatos cobertos pelo contrato:

- preço simples/completo;
- moeda separada + valor completo;
- inteiro + centavos (legado);
- varejo/normal;
- App/Clube;
- atacado/wholesale;
- quantidade mínima;
- unidade;
- limite CPF;
- formatação `19.90` → `19,90`, `19,90` → `19,90` e composição `R$` conforme o template original.

O texto original do template é preservado em `node.metadata["binding_template_text"]`, evitando que uma segunda substituição de produto use o valor já renderizado como novo template.

## Smart Slots

Invariantes implementados:

- `product_id` e `product_snapshot` são atualizados juntos;
- `extra_bindings` fazem parte do binding real, não apenas metadata passiva;
- replacement não move a geometria;
- imagens são propriedade do produto ligado ao slot e não podem herdar silenciosamente a foto anterior;
- slots bloqueados não recebem cascade;
- detach é persistente via metadata;
- rebind remove o estado detached;
- duplicação multipágina remapeia IDs e mantém snapshots independentes;
- rebuild semântico preserva estado de slots recuperados.

## Persistência e schema esperado

Não foi alterado o serializer core do CHAT 3. O contrato utiliza somente campos já serializáveis em SR Scene 2.

### SmartSlot

```json
{
  "id": "slot-id",
  "page_id": "page-id",
  "product_id": "produto-1",
  "node_by_role": {
    "name": "node-name",
    "image": "node-image",
    "price_complete": "node-price",
    "quantity": "node-quantity"
  },
  "metadata": {
    "product_snapshot": {
      "id": "produto-1",
      "display_name": "CAFÉ 500G",
      "price": "19,90",
      "metadata": {
        "description": "TORRA MÉDIA"
      }
    },
    "extra_bindings": {
      "app_price_complete": ["node-app"],
      "wholesale_price": ["node-wholesale"]
    }
  }
}
```

### Node detached

```json
{
  "metadata": {
    "smart_slot_detached": true,
    "detached_from_slot_id": "slot-id"
  }
}
```

### Necessidade para CHAT 3

O serializer central deve apenas continuar preservando sem perda:

- `SmartSlot.node_by_role` com chaves string conhecidas/desconhecidas;
- `SmartSlot.metadata.extra_bindings` como `dict[str, list[str]]`;
- `SmartSlot.metadata.product_snapshot` como objeto JSON;
- metadata arbitrária dos nodes, incluindo `binding_template_text`, `smart_slot_detached` e `detached_from_slot_id`.

O modelo atual já aparenta suportar essas estruturas; não foi necessária refatoração do serializer nesta branch. O gate de integração deve confirmar save → load → update → save em ambiente real do CHAT 3.

## Dependências de integração

### CHAT 1 — Renderer/fidelidade

O CHAT 4 entrega ao renderer propriedades visuais atualizadas (`text`, `visible`, `asset_id`, `style`, transform preservado). Se essas propriedades estiverem corretas na SR Scene mas o raster estiver incorreto, o bug é do CHAT 1. Nenhuma rotina de rasterização foi modificada aqui.

### CHAT 2 — PPTX/Canva import

Nenhum parser Office/PPTX/Canva foi alterado. O CHAT 4 apenas interpreta nomes semânticos já existentes nos nodes SR Scene, como:

- `SR_PRODUTO`
- `SR_PRECO_VAREJO` / `SR_PRECO_PROMO`
- `SR_PRECO_CLUBE` / App
- `SR_PRECO_ATACADO`
- `SR_QUANTIDADE_ATACADO`
- `SR_UNIDADE_*`
- `SR_LIMITE`

O pipeline Excel existente já normaliza Promoção/Varejo/Atacado/Quantidade/Limite/Validade para o modelo Product; não foi duplicada essa responsabilidade.

### CHAT 3 — Editor QML/persistência core

Integração recomendada no QML:

- criar ProductCard → `create_product_card`;
- arrastar produto → `drop_product` existente;
- trocar produto diretamente → `bind_product`;
- editar somente o card → `update_product_fields`;
- editar cadastro e refletir em todos os cards → `update_product_data`;
- reconfigurar campo → `rebind_slot`;
- desvincular → `remove_smart_slot`.

Não é necessário o QML manipular `node_by_role` internamente para o fluxo comum.

## Testes essenciais cobertos por código

### ProductCard

- create → fill → edit → replace;
- descrição/imagem/preço/quantidade/validade;
- geometria preservada;
- múltiplos cards sem estado compartilhado.

### PriceBlock

- preço simples/completo;
- varejo;
- atacado;
- App/Clube;
- quantidade;
- decimal ponto/vírgula;
- alteração dinâmica;
- API canônica e slot importado.

### SmartSlot

- bind;
- drop;
- replace;
- detach;
- rebuild sem reaparecer;
- rebind;
- lock;
- duplicação multipágina.

### Bindings

- create;
- update;
- remove;
- duplicate via página com IDs novos;
- rebind;
- referência inexistente;
- `extra_bindings` órfão;
- update em cascata;
- imagem em cascata;
- no-op sem novo histórico.

### Persistência

- `GraphicsDocument.to_dict()` / `from_dict()` para ProductCard ligado;
- `product_snapshot`;
- `extra_bindings`;
- `binding_template_text`;
- estado detached;
- duplicação com cópia profunda de snapshot.

## Gate de validação criado

Workflow: `.github/workflows/g2-product-system.yml`

Etapas previstas:

1. Windows + Python 3.11;
2. instalação `.[dev,graphics2]`;
3. `python -m compileall -q src/srstudio/graphics2`;
4. Ruff restrito ao escopo CHAT 4;
5. pytest dos contratos ProductCard/PriceBlock/SmartSlot/bindings e compatibilidade de SmartSlot Canva.

### Status de execução

**Não observado/executado nesta sessão devido à ausência de checkout local e à limitação do conector para runs disparados por push.** Esse é o principal gate pendente antes da integração.

## Critério de integração

Antes do merge da branch paralela, executar em checkout real:

```powershell
python -m compileall -q src/srstudio/graphics2
python -m ruff check src/srstudio/graphics2 tests
python -m pytest -q -ra tests/test_graphics2_core.py tests/test_graphics2_complete_price_recovery.py tests/test_graphics2_product_system.py tests/test_graphics2_product_card_creation.py tests/test_graphics2_product_data_cascade.py tests/test_graphics2_product_command_compat.py tests/test_graphics2_product_page_duplicate.py tests/test_graphics2_slot_detach.py tests/test_graphics2_wholesale_price_slot.py tests/test_graphics2_canonical_commercial_priceblocks.py tests/test_graphics2_binding_integrity.py tests/test_graphics2_named_slot_v2_migration.py tests/test_graphics2_semantic_product_card.py tests/test_graphics2_named_multi_price_slot.py tests/test_graphics2_named_limit_slot.py tests/test_graphics2_page_duplicate.py tests/test_canva_smart_slot_bindings.py
```

Se esse gate passar, o backend do CHAT 4 estará pronto para integração com o QML/persistência do CHAT 3 e para validação visual pelo CHAT 1.
