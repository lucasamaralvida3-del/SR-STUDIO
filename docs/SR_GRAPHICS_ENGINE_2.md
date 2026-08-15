# SR Graphics Engine 2.0

## Objetivo

O SR Graphics Engine 2.0 substitui progressivamente o editor visual antigo sem repetir sua arquitetura. O documento passa a existir em um modelo de cena próprio (`srscene/2.0`), independente de zoom, DOM, resolução de monitor, PowerPoint ou biblioteca de renderização.

A migração é **paralela e reversível**: o editor atual continua disponível até que os gates de paridade visual e funcional sejam aprovados.

## Arquitetura

1. **SR Scene 2** — fonte única de verdade para páginas, nós, grupos, Smart Slots, assets, guias e bindings de produto.
2. **GraphicsSession** — operações transacionais de edição. Mover, redimensionar, rotacionar, alinhar, distribuir, agrupar, camadas, lock, hide, duplicar, crop, texto, páginas e preenchimento de produto usam a mesma API independentemente da UI.
3. **TransactionHistory** — undo/redo por snapshots atômicos. O foco inicial é integridade; otimizações estruturais só entram depois de testes de equivalência.
4. **SR Scene Package** — `.srscene` ZIP com `scene.json`, manifesto, hashes e assets opcionais. Salvamento é atômico.
5. **Preflight** — valida árvore, vínculos, ciclos, dimensões, assets, fontes e elementos fora da página.
6. **Compatibility Layer** — converte `StudioProject` 5.x e o contrato legado do Encartes para SR Scene 2, permitindo adoção gradual.
7. **Qt Quick GPU Host** — front-end opcional via PySide6. O documento continua independente do renderer.

## Paridade obrigatória antes de substituir o editor atual

- produtos com imagem e busca;
- Excel/XLSX;
- Canva/PPTX;
- Smart Slots e preenchimento por clique/drag-and-drop;
- preço separado em moeda, reais, centavos e unidade;
- limite por CPF;
- múltiplas páginas e duplicar página;
- destaque/categorias/layout automático;
- seleção múltipla;
- mover/redimensionar/rotacionar;
- agrupamento;
- alinhamento/distribuição;
- snap, grid, régua e guias;
- camadas;
- bloquear/ocultar;
- crop/zoom/foco/flip de imagem;
- edição de texto;
- fontes manuais e fallback controlado;
- undo/redo;
- histórico e autosave;
- validação/preflight;
- PDF/PNG de alta resolução;
- Banco de Imagens + cache/cloud sync;
- SR IA/Template Learning;
- Promoções, Atacado e compatibilidade com projetos existentes.

## Gates

O Engine 2 só vira padrão quando os testes antigos e novos estiverem verdes, o corpus real de layouts Canva atingir o limite de fidelidade visual, round-trip `.srscene` preservar a geometria, undo/redo for determinístico e preview/export consumirem o mesmo SR Scene.

## Repositório

O motor nasce em `feature/sr-graphics-engine-2` para ficar isolado do canal Beta. Separar em outro repositório pode ser feito depois sem mudar o formato SR Scene 2, pois o pacote foi desenhado como subsistema independente.
