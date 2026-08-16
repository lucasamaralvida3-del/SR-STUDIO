# SR Graphics Engine 2.0

## Objetivo

O SR Graphics Engine 2.0 substitui progressivamente o editor visual antigo sem repetir sua arquitetura. O documento passa a existir em um modelo de cena próprio (`srscene/2.0`), independente de zoom, DOM, resolução de monitor, PowerPoint ou biblioteca de renderização.

A migração é **paralela e reversível**: o editor atual continua disponível até que os gates de paridade visual e funcional sejam aprovados.

## Arquitetura

1. **SR Scene 2** — fonte única de verdade para páginas, nós, grupos, Smart Slots, assets, guias e bindings de produto.
2. **GraphicsSession** — operações transacionais de edição. Mover, redimensionar, rotacionar, alinhar, distribuir, agrupar, camadas, lock, hide, duplicar, crop, texto, páginas e preenchimento de produto usam a mesma API independentemente da UI.
3. **TransactionHistory** — undo/redo por snapshots atômicos. O foco inicial é integridade; otimizações estruturais só entram depois de testes de equivalência.
4. **SR Scene Package** — `.srscene` ZIP com `scene.json`, manifesto, hashes, assets e fontes do projeto. Salvamento é atômico e as fontes PPTX permanecem portáteis dentro do projeto, sem instalação global no Windows.
5. **Preflight** — valida árvore, vínculos, ciclos, dimensões, assets, fontes e elementos fora da página.
6. **Compatibility Layer** — converte `StudioProject` 5.x e o contrato legado do Encartes para SR Scene 2, permitindo adoção gradual.
7. **Qt Quick GPU Host** — front-end opcional via PySide6. O documento continua independente do renderer.
8. **Visual Fidelity Lab** — compara Golden Master e renderer por cor, luminância, bordas, pixels, área alterada, MAE e RMS.
9. **Production Gate** — combina preflight, Import Audit, fidelidade OOXML, fontes embutidas e resultado visual antes de permitir promoção do Engine 2.

## Fase 2 — Paridade visual e confiabilidade

A importação Canva/PPTX possui uma segunda passagem OOXML dedicada à fidelidade. Ela relê o arquivo original sem alterar a geometria x/y/w/h já convertida para SR Scene 2 e recupera informações que não podem ser descartadas: fontes embutidas, `spAutoFit`, insets, espaçamento entre caracteres, line spacing, `custGeom` e máscaras de imagem.

Fontes `.fntdata`/EOT do PowerPoint são extraídas para TTF/OTF quando o `fsType` permitir uso no documento. O Qt registra essas fontes somente no processo com `QFontDatabase.addApplicationFont`; o sistema operacional não é alterado. Quando o projeto é salvo em `.srscene`, as fontes entram no ZIP com hash SHA-256 e voltam a ser extraídas no carregamento.

O renderer de produção usa `QPainterPath` para formas DrawingML customizadas e pode aplicar o mesmo caminho como clip de imagens. Isso evita transformar formas curvas do Canva em retângulos arredondados aproximados.

### Caso de referência Quinta Filé

O arquivo real `OFERTAS QUINTA FILÉ NOVO.pptx` foi analisado localmente e não é versionado no repositório. Ele usa as fontes embutidas Anton e High Cruiser, caixas com auto-fit/espaçamento e muitas geometrias customizadas. Esses recursos foram usados para definir o primeiro conjunto de correções da Fase 2.

### Golden Master multipágina

Para um teste oficial, use o PPTX original junto da exportação PDF do próprio Canva/PowerPoint:

```bash
sr-pptx-golden-master "OFERTAS QUINTA FILÉ NOVO.pptx" "OFERTAS QUINTA FILÉ NOVO.pdf" \
  --target-width 2160 \
  --save-scene \
  --out build/golden-master/quinta-file
```

O pipeline executa `PPTX -> Import Pipeline -> SR Scene 2 -> Qt Renderer`, rasteriza cada página do PDF oficial com PDFium na mesma largura, compara página a página, gera PNG candidato, diff e relatório JSON, e usa **o pior score entre as páginas** no Production Gate. Divergência de quantidade de páginas também reprova o gate.

Para diagnóstico sem PDF de referência:

```bash
sr-fidelity-lab pptx-audit "arquivo.pptx" --save-scene
```

Para comparar apenas uma página com uma imagem de referência:

```bash
sr-fidelity-lab pptx-render-compare "arquivo.pptx" "pagina-1.png" --page 0 --save-scene
```

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

O Engine 2 só vira padrão quando os testes antigos e novos estiverem verdes, o corpus real de layouts Canva atingir o limite de fidelidade visual, round-trip `.srscene` preservar a geometria e recursos do documento, undo/redo for determinístico e preview/export consumirem o mesmo SR Scene.

No modo de release, `ProductionGateReport` exige uma comparação visual aprovada. Um documento também é bloqueado se houver erros estruturais, falha no Import Audit, fonte PPTX declarada mas não extraída, Golden Master ausente/reprovado ou score abaixo do mínimo.

## Repositório

O motor nasce em `feature/sr-graphics-engine-2` para ficar isolado do canal Beta. Separar em outro repositório pode ser feito depois sem mudar o formato SR Scene 2, pois o pacote foi desenhado como subsistema independente.
