# CHAT 4 — ProductCards + PriceBlocks + Smart Slots + Bindings

## Identificação e isolamento

- Repositório: `lucasamaralvida3-del/SR-STUDIO`
- Linha G2 usada como base: `g2/chatgpt-professional-usable`
- `BASE_SHA`: `89c91da05922d080453dcf42489dc671091bf671`
- Branch exclusiva: `g2/parallel-product-system`
- Checkpoint de implementação imediatamente antes deste refresh de documentação: `41` commits à frente e `0` atrás do `BASE_SHA`, com `23` arquivos no delta.
- O commit deste próprio refresh documental é posterior ao checkpoint acima; o estado autoritativo final deve ser lido pelo intervalo `89c91da05922d080453dcf42489dc671091bf671..g2/parallel-product-system`.
- `main` e `stable`: não alterados por este CHAT 4.
- Nenhuma branch paralela foi mesclada.
- Nenhum `reset --hard`, `clean` destrutivo ou descarte de trabalho foi usado.

### Limitação do ambiente desta sessão

O checkout local do SR-STUDIO não estava montado no container desta sessão e o container não conseguia resolver `github.com`. Portanto não foi possível criar fisicamente o worktree solicitado em `../SR-STUDIO-g2-product-system`, nem executar `git status`, `ruff` ou `pytest` localmente. O isolamento foi mantido pelo conector GitHub: a branch `g2/parallel-product-system` foi criada exatamente no `BASE_SHA` e todas as escritas foram feitas somente nela.

Também não foi possível observar um run disparado por `push` do GitHub Actions pelo conector disponível nesta sessão. Consequentemente, os testes abaixo foram escritos e adicionados ao gate CI, porém este relatório **não afirma que passaram em execução real**. Antes do merge é obrigatório executar o workflow `G2 Product System` ou os comandos equivalentes em um checkout normal.

## Objetivo entregue

Foi criada uma camada inteligente G2 de produção de encartes que não depende de detalhes internos do QML. O backend agora suporta o fluxo:

`criar ProductCard → vincular produto → editar/trocar dados → atualizar imagem/preços/quantidade → preservar layout → atualizar localmente ou em cascata → duplicar/religar/remover sem referências inválidas`.

O contrato cobre nome, descrição, imagem, preço normal/varejo, App/Clube, Atacado/Wholesale, quantidade, unidade, limite CPF e validade quando esses campos existem no slot. Campos opcionais são limpos quando o produto substituto não os possui, evitando que dados do produto anterior permaneçam visíveis.

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
- `tests/test_graphics2_product_auxiliary_fields.py`
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

## Histórico de commits

A implementação foi feita em ciclos pequenos. Alguns commits confirmados durante a sessão:

- `629976118769...` — `fix(g2): unify product binding runtime`
- `486fc8a5a8cf...` — testes de binding comercial e isolamento
- `d7052f264058...` — regressão de preço completo recuperado
- `f08442e041bc...` — estados, round-trip e duplicação de ProductCard
- `1fd3966640c5...` — gate CI inicial do Product System
- `184a56313928...` — recuperação de Atacado/Quantidade em slots nomeados
- `f7596c495e67...` — runtime de PriceBlock comercial
- `bce912255479...` — integração dos PriceBlocks comerciais ao rebuild
- `f0a5fbbf0faf...` — testes Varejo/Atacado/Quantidade
- `ba382eb072b5...` — preflight de bindings órfãos
- `f076b5267284...` — testes de integridade de binding
- `4e471ce724d4...` — preservação do ID estável `named-slot-v2`
- `8ca58936bee7...` — migração em-place de SmartSlot nomeado v2
- `b4162f2fdee9...` — testes de migração v2 → v3
- `c539ec12b86f...` — criação de ProductCard e comandos de backend
- `63fbec02977a...` — comandos ProductCard transacionais e seguros
- `e98b1b69efc4...` — ativação da API ProductCard no pacote G2
- `12ea4dfe62af...` — testes end-to-end de criação/edição/troca
- `5756675f7a49...` — correção de acesso a campo inexistente no relatório semântico
- `d36dbde24738...` — ampliação do gate CHAT 4
- `f99177d384db...` — proteção de nodes detached na recuperação semântica
- `18eaf665b674...` — remoção persistente de SmartSlot
- `5b74747c4cae...` — gate incluindo os contratos de campos auxiliares de ProductCard

Os ciclos intermediários também adicionaram atualização local/cascata de produto, compatibilidade `drop_product`, reativação por `rebind`, cascata de imagem, PriceBlocks canônicos Varejo/Atacado, duplicação completa de ProductCard e persistência de descrição/validade na associação semântica após rebuild.

O histórico completo e autoritativo é:

`89c91da05922d080453dcf42489dc671091bf671..g2/parallel-product-system`

## Bugs e prioridades

### P0

- Durante a revisão do próprio patch foi detectado um acesso a `SemanticBlockReport.protected_product_nodes`, campo inexistente. Isso quebraria `build_semantic_blocks()` em cards comerciais. O acesso foi removido antes da integração (`5756675f7a49...`).
- Nenhum outro P0 conhecido permaneceu após a revisão estática, mas, pela ausência de execução real do gate nesta sessão, não é correto declarar P0=zero de forma definitiva.

### P1 corrigidos

1. **Preço completo recuperado podia desaparecer ao trocar produto.** Slots recuperados usavam `retail_price`, enquanto o binder anterior não formatava esse papel. `retail_price` e `price_complete` agora seguem o mesmo contrato.
2. **Foto do produto anterior podia permanecer.** Se o substituto não tem imagem, `asset_id`/`bound_image_source` são limpos e o node fica oculto.
3. **Campos opcionais antigos podiam permanecer.** App price, Atacado, Quantidade, Limite, Validade e Descrição são esvaziados/ocultos quando ausentes.
4. **`extra_bindings` podiam ficar órfãos.** Remoção de node limpa referências e o preflight acusa bindings primários/extras ausentes ou slot em página errada.
5. **Varejo + Atacado + Quantidade não formavam um componente comercial completo.** A camada G2 reconhece esses papéis e produz PriceBlocks vinculados ao mesmo ProductCard.
6. **API canônica e template importado tinham semântica diferente.** `BindingRole.RETAIL_PRICE` gera PriceBlock principal e `BindingRole.WHOLESALE_PRICE` gera PriceBlock de Atacado.
7. **Migração de slot nomeado podia trocar o ID.** A capacidade semântica passou para metadata v3, mas o sal do ID permanece `named-slot-v2` para compatibilidade com documentos já salvos.
8. **SmartSlot v2 salvo não ganhava Atacado/Quantidade sem recriação.** O upgrade é em-place, preservando `slot.id`, `product_id`, `locked` e `product_snapshot`.
9. **Remover SmartSlot mantendo os visuais podia recriá-lo no próximo rebuild.** Nodes detached ficam temporariamente fora da recuperação automática e preservam sua visibilidade final.
10. **Rebind de nodes detached podia manter estado residual.** Binding/rebind explícito remove os marcadores de detach.
11. **Atualização compartilhada não propagava entre páginas.** `update_product_data()` atualiza catálogo e todos os slots desbloqueados ligados ao mesmo produto em uma única transação.
12. **Duplicação precisava preservar independência.** `node_by_role`, `extra_bindings`, snapshots e IDs são cobertos por testes específicos de página duplicada.
13. **Wrappers novos podiam quebrar o drag-and-drop legado.** O encadeamento `drop_product → bind_product` permanece compatível e preserva o payload `drop_target`.
14. **Descrição e validade podiam sair do `members` do ProductCard após rebuild.** Embora os nodes continuassem ligados ao SmartSlot, o builder histórico não tratava esses papéis como membros do card. O pós-processamento comum agora reinsere `description`, `product_description`, `validity` e `quantity` vindos de bindings primários ou extras e recalcula a geometria do ProductCard em todo rebuild. Há testes com rebuild repetido e com `metadata.description` atualizado dinamicamente.

### P2 / limitações conhecidas

- O modelo central `Product` não possui campo dedicado `description`. O G2 aceita `product["description"]` em chamadas diretas e, para persistência compatível com o modelo atual, usa `product.metadata["description"]` como formato recomendado.
- A UI/QML para expor os novos comandos pertence ao CHAT 3.
- Nenhuma refatoração do serializer core foi feita. O contrato usa estruturas já serializáveis: `metadata`, `node_by_role`, `extra_bindings` e `product_snapshot`.

### P3

- Labels/controles específicos de UI para Varejo, Atacado e App podem ser refinados no CHAT 3 sem mudar o contrato de backend.

## Contrato de ProductCard

### Criar

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
    "include_wholesale": True
}
```

Retorna `slot_id`, `product_card_id`, `node_by_role` e `extra_bindings`.

### Vincular/substituir produto

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

### Editar apenas um card

```python
{
    "name": "update_product_fields",
    "slot_id": "slot-id",
    "changes": {
        "display_name": "CAFÉ DESTAQUE 500G",
        "price": "18,99",
        "metadata": {"description": "TORRA MÉDIA"}
    }
}
```

Esse comando altera o snapshot/visual somente daquele card e não modifica o registro compartilhado em `document.metadata["products"]`.

### Atualizar produto compartilhado em cascata

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

O resultado inclui `slots_updated`, `slots_skipped_locked`, `catalog_updated` e `page_ids`.

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

### Remover/desvincular

```python
{
    "name": "remove_smart_slot",
    "slot_id": "slot-id",
    "delete_nodes": False
}
```

Com `delete_nodes=False`, os visuais são preservados e recebem marcação de detach. Com `delete_nodes=True`, os nodes ligados são removidos.

## PriceBlocks

Formatos cobertos:

- preço simples/completo;
- moeda separada + valor completo;
- inteiro + centavos legado;
- Varejo/Normal;
- App/Clube;
- Atacado/Wholesale;
- quantidade mínima;
- unidade;
- limite CPF;
- formatação decimal com ponto ou vírgula;
- atualização dinâmica sem mudança de geometria.

O texto original do template é preservado em `node.metadata["binding_template_text"]`, evitando que uma segunda substituição use o valor já renderizado como novo template.

## Smart Slots e bindings

Invariantes implementados:

- `product_id` e `product_snapshot` são atualizados juntos;
- `extra_bindings` participam do binding real;
- replacement não move a geometria;
- imagens pertencem ao produto ligado ao slot e não podem herdar silenciosamente a foto anterior;
- slots bloqueados não recebem cascade;
- detach é persistente via metadata;
- rebind remove o estado detached;
- duplicação multipágina remapeia IDs e mantém snapshots independentes;
- rebuild semântico preserva estado de slots recuperados;
- descrição, validade e quantidade permanecem membros do ProductCard após rebuild;
- referência inexistente é rejeitada ou acusada no preflight.

## Persistência e schema esperado

Não foi alterado o serializer core do CHAT 3. O contrato usa somente campos já serializáveis em SR Scene 2.

### Exemplo de SmartSlot

```json
{
  "id": "slot-id",
  "page_id": "page-id",
  "product_id": "produto-1",
  "node_by_role": {
    "name": "node-name",
    "image": "node-image",
    "price_complete": "node-price",
    "description": "node-description",
    "quantity": "node-quantity",
    "validity": "node-validity"
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

### Exemplo de node detached

```json
{
  "metadata": {
    "smart_slot_detached": true,
    "detached_from_slot_id": "slot-id"
  }
}
```

### Necessidade para CHAT 3

O serializer central deve continuar preservando sem perda:

- `SmartSlot.node_by_role` com chaves string conhecidas ou estendidas;
- `SmartSlot.metadata.extra_bindings` como `dict[str, list[str]]`;
- `SmartSlot.metadata.product_snapshot` como objeto JSON;
- metadata arbitrária dos nodes, incluindo `binding_template_text`, `smart_slot_detached` e `detached_from_slot_id`.

O modelo atual aparenta suportar essas estruturas e os testes de `to_dict()`/`from_dict()` foram escritos. O gate de integração do CHAT 3 deve confirmar save → load → update → save no ambiente real.

## Dependências de integração

### CHAT 1 — Renderer/fidelidade

O CHAT 4 entrega `text`, `visible`, `asset_id`, `style` e transforms preservados. Se essas propriedades estiverem corretas na SR Scene e o raster estiver incorreto, o problema pertence ao CHAT 1. Nenhuma rasterização foi modificada aqui.

### CHAT 2 — PPTX/Canva import

Nenhum parser Office/PPTX/Canva foi alterado. O CHAT 4 só interpreta nomes semânticos já existentes nos nodes SR Scene, por exemplo:

- `SR_PRODUTO`
- `SR_PRECO_VAREJO` / `SR_PRECO_PROMO`
- `SR_PRECO_CLUBE` / App
- `SR_PRECO_ATACADO`
- `SR_QUANTIDADE_ATACADO`
- `SR_UNIDADE_*`
- `SR_LIMITE`

O pipeline Excel existente já normaliza Promoção/Varejo/Atacado/Quantidade/Limite/Validade para `Product`; essa responsabilidade não foi duplicada.

### CHAT 3 — Editor QML/persistência core

Integração recomendada:

- criar ProductCard → `create_product_card`;
- arrastar produto → `drop_product` existente;
- trocar produto diretamente → `bind_product`;
- editar somente o card → `update_product_fields`;
- editar cadastro e refletir em todos os cards → `update_product_data`;
- reconfigurar campo → `rebind_slot`;
- desvincular/remover → `remove_smart_slot`.

O QML não precisa manipular `node_by_role` diretamente no fluxo comum.

## Testes essenciais cobertos por código

### ProductCard

- criar → preencher → editar → substituir;
- nome, descrição, imagem, preço, quantidade e validade;
- geometria preservada;
- múltiplos cards sem compartilhamento indevido de estado;
- descrição/validade mantidas no ProductCard após múltiplos rebuilds;
- descrição persistida em `metadata.description` e atualizada dinamicamente.

### PriceBlock

- preço simples/completo;
- Varejo;
- Atacado;
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

Etapas:

1. Windows + Python 3.11;
2. instalação `.[dev,graphics2]`;
3. `python -m compileall -q src/srstudio/graphics2`;
4. Ruff restrito ao escopo CHAT 4;
5. pytest dos contratos ProductCard/PriceBlock/SmartSlot/bindings e compatibilidade do SmartSlot Canva.

O gate inclui também `tests/test_graphics2_product_auxiliary_fields.py`, cobrindo especificamente descrição/validade em rebuild e `metadata.description`.

### Status de execução

**Não executado/observado nesta sessão**, devido à ausência de checkout local e à limitação do conector para runs disparados por push. Esse é o principal gate pendente antes da integração.

## Comando recomendado antes do merge

```powershell
python -m compileall -q src/srstudio/graphics2
python -m ruff check src/srstudio/graphics2 tests
python -m pytest -q -ra tests/test_graphics2_core.py tests/test_graphics2_complete_price_recovery.py tests/test_graphics2_product_system.py tests/test_graphics2_product_card_creation.py tests/test_graphics2_product_data_cascade.py tests/test_graphics2_product_command_compat.py tests/test_graphics2_product_page_duplicate.py tests/test_graphics2_product_auxiliary_fields.py tests/test_graphics2_slot_detach.py tests/test_graphics2_wholesale_price_slot.py tests/test_graphics2_canonical_commercial_priceblocks.py tests/test_graphics2_binding_integrity.py tests/test_graphics2_named_slot_v2_migration.py tests/test_graphics2_semantic_product_card.py tests/test_graphics2_named_multi_price_slot.py tests/test_graphics2_named_limit_slot.py tests/test_graphics2_page_duplicate.py tests/test_canva_smart_slot_bindings.py
```

Se esse gate passar em checkout real, o backend do CHAT 4 estará pronto para integração com o QML/persistência do CHAT 3 e para validação visual pelo CHAT 1.
