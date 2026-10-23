# G2 — Limpeza Azul: perfil canônico de UM slot (Beta candidata)

## Objetivo e origem
Referência: captura 960×800 fornecida pelo usuário. Elementos: cabeçalho com nome do produto; moldura azul e área branca da imagem; selo pequeno NA PROMOÇÃO e preço dividido; bloco inferior NO CLUBE com R$, inteiro, centavos e unidade independentes.

A captura serviu para estimar posições RELATIVAS. Não é uma importação de PPTX nem uma certificação pixel-a-pixel. Molduras decorativas nunca devem virar outros SmartSlots.

## Contrato semântico

| Componente | Papel | Onde |
|---|---|---|
| limpeza-blue-v1 | Preset único no menu ItemSlot | slot_limpeza_blue.py |
| name, image | Nome e imagem independentes | node_by_role |
| price_reais, price_cents, currency, unit | Preço PRINCIPAL: clube | node_by_role |
| promotion_label | Rótulo NA PROMOÇÃO | extra_bindings |
| promotion_currency, promotion_integer, promotion_cents, promotion_unit | Preço SECUNDÁRIO: promoção | extra_bindings |
| club_label | Rótulo NO CLUBE | extra_bindings |
| white_panel, promotion_background, club_background | Artwork decorativo, não outro slot | decorative_nodes |

Card base: 867×664 unidades. Posições e cores são estimativas editáveis.

## UI e bindings

- add_item_slot com preset_id=limpeza-blue-v1 adiciona um card editável.
- bind_product aceita name, price e opcionalmente club_price, app_price, promotion_price, unit, promotion_unit, promotion_label e club_label.
- Valor principal: club_price > app_price > price.
- Valor secundário: promotion_price > price.
- inspect_limpeza_blue_slot verifica a integridade dos campos existentes sem modificar a cena.
- Se só houver price, ambos os preços usam o mesmo valor. Preços distintos exigem atributos específicos.

## Checklist de teste manual

1. Abrir G2 e adicionar LIMPEZA · AZUL · 2 PRECOS pelo menu ItemSlot.
2. Aplicar um produto com nome longo, imagem, preço promocional e preço de clube distintos.
3. Conferir geometria, cabeçalho, legibilidade e separação entre preços.
4. Duplicar SEM produto, verificar placeholders e original inalterado.
5. Salvar e reabrir .srscene; exportar PNG/PDF e comparar preview e exportação.

## Gates antes de promover o canal Beta

- CI Python e regressão G2.
- Runtime Windows Qt Quick e testes de exportação.
- Verificação visual do card e aprovação manual.
- Bundle Windows íntegro, SHA-256, URL pública validada e ativação do manifesto SOMENTE por último.
- Não alterar main/stable nem substituir o binário Beta 35 enquanto pendente.

## Limitações deliberadas

O reconhecimento implementado é estrutural para o ItemSlot criado com esse perfil: não é OCR e não reconhece automaticamente PNG ou PPTX arbitrário. O ZIP do Codex não foi incorporado, pois a ferramenta de extração deste ambiente não conseguiu abrir o conteúdo. A fidelidade exata à fonte será avaliada antes da promoção.
