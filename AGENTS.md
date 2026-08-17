# Constituição de Engenharia do SR Studio

Estas instruções se aplicam a todo o repositório. Decisões locais podem detalhá-las, mas não contrariá-las.

## Identidade do produto

SR Studio é uma plataforma profissional de automação e criação de materiais promocionais para supermercado.

O sistema possui módulos desktop e um novo motor gráfico chamado SR Graphics Engine 2.0.

## Fonte de verdade

- SR Graphics Engine 2.0 é o Studio de Encartes principal e a linha oficial de evolução.
- Beta 7.29 Professional é baseline histórica de compatibilidade e fallback.
- O editor legado não deve substituir `src/srstudio/graphics2/` nem seus componentes QML.
- Ao integrar código histórico, preserve primeiro os contratos e comportamentos comprovados; não restaure a arquitetura antiga como núcleo do produto.

## Compatibilidade

Nunca quebrar silenciosamente:

- `.srproject`;
- `.srscene`;
- Excel;
- PPTX/Canva;
- templates;
- produtos;
- banco de imagens;
- preços;
- UN/KG;
- limite por CPF;
- preço aplicativo;
- Promoções;
- Atacado;
- PDF;
- projetos anteriores.

Mudanças deliberadamente incompatíveis exigem migração explícita, testes de round-trip e documentação.

## Graphics Engine

Toda nova evolução do Studio de Encartes deve priorizar:

- SR Scene 2;
- scene graph canônico;
- Command Router;
- Qt Quick/PySide6;
- renderização GPU quando apropriado;
- preview e exportação semanticamente equivalentes;
- operações assíncronas;
- Golden Masters;
- Visual Fidelity Lab;
- undo/redo;
- snapshots;
- Production Gate.

Não reintroduzir Tk Canvas como núcleo do novo editor. O editor legado pode permanecer somente como fallback e adaptador de compatibilidade.

## Novo Studio de Encartes

Preservar e evoluir:

- seleção;
- mover;
- resize;
- rotação;
- duplicação;
- exclusão;
- texto;
- imagens;
- shapes;
- layers;
- snapping;
- guias;
- grid;
- múltiplas páginas;
- reordenação;
- duplicação de página;
- undo/redo;
- ProductCards;
- PriceBlocks;
- Smart Slots;
- biblioteca de produtos;
- drag-and-drop;
- importação Excel;
- PPTX/Canva;
- imagens de produto;
- preço em reais e centavos;
- unidade;
- limite por CPF;
- preço aplicativo;
- exportação PDF/PNG.

## Qualidade

Toda mudança relevante deve:

- possuir testes;
- passar regressão;
- respeitar undo/redo;
- não bloquear a thread de UI;
- não introduzir I/O pesado durante drag;
- evitar redraw total quando possível;
- preservar Golden Masters;
- impedir divergência silenciosa entre preview e exportação.

Não remover, relaxar ou ignorar teste anteriormente aprovado apenas para deixar um pipeline verde. Investigue a causa da falha e preserve o contrato correto.

## SR IA

A futura SR IA nunca deve modificar a cena diretamente.

Fluxo obrigatório:

```text
pedido
  -> proposta estruturada
  -> validação
  -> preview/diff
  -> Command Router
  -> execução
  -> undo/redo
```

## Cloud readiness

Não migrar para cloud agora. Novas decisões, porém, não devem impedir a futura arquitetura híbrida.

Preservar:

- SR Scene serializável;
- assets por ID/URI/hash;
- banco de produtos atrás de interface;
- jobs assíncronos;
- comandos serializáveis;
- adaptadores separados para desktop e futura API.

O núcleo de domínio não deve depender de caminhos locais, widgets ou detalhes de transporte quando uma referência estável puder ser usada.

## Git

- nunca trabalhar diretamente em `main`;
- usar branches com escopo claro;
- preservar tags e branches históricas;
- não disparar release sem autorização explícita;
- executar testes antes de concluir;
- manter commits pequenos e com escopo claro;
- preferir merge real quando a relação histórica precisa ser preservada;
- não rebasear ou sobrescrever a história oficial sem autorização explícita.
