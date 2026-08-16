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
7. **Qt Quick GPU Host** — front-end opcional via PySide6. O documento continua independente do renderer e o host pode abrir diretamente PPTX/XLSX ou `.srscene`.
8. **Visual Fidelity Lab** — compara Golden Master e renderer por cor, luminância, bordas, pixels, área alterada, MAE e RMS.
9. **Production Gate** — combina preflight, Import Audit, fidelidade OOXML, fontes embutidas e resultado visual antes de permitir promoção do Engine 2.
10. **Studio Bridge** — abre o Engine 2 em processo separado a partir do shell Tk atual somente quando a feature flag é habilitada, sem misturar os event loops Tk/Qt e sem substituir o editor estável.

## Fase 2 — Paridade visual e confiabilidade

A importação Canva/PPTX possui uma segunda passagem OOXML dedicada à fidelidade. Ela relê o arquivo original sem alterar a geometria x/y/w/h já convertida para SR Scene 2 e recupera informações que não podem ser descartadas: fontes embutidas, `spAutoFit`, insets, espaçamento entre caracteres, line spacing, `custGeom` e máscaras de imagem.

Fontes `.fntdata`/EOT do PowerPoint são extraídas para TTF/OTF quando o `fsType` permitir uso no documento. O Qt registra essas fontes somente no processo com `QFontDatabase.addApplicationFont`; o sistema operacional não é alterado. Quando o projeto é salvo em `.srscene`, as fontes entram no ZIP com hash SHA-256 e voltam a ser extraídas no carregamento.

O renderer de produção usa `QPainterPath` para formas DrawingML customizadas e pode aplicar o mesmo caminho como clip de imagens. Isso evita transformar formas curvas do Canva em retângulos arredondados aproximados.

### Preview de imagem com o mesmo contrato da exportação

A partir da `2.0.0-alpha.19`, o canvas principal não depende apenas de `Image.PreserveAspectFit/PreserveAspectCrop` para produtos importados. O host registra o provider `image://srscene`, que produz um preview composto a partir do SR Scene usando:

- crop persistido;
- `contain`, `cover` ou `fill`;
- zoom;
- foco X/Y;
- flip horizontal/vertical com compensação correta de foco;
- dimensão/aspect ratio exatos do node.

O provider usa snapshots imutáveis protegidos por lock. `requestImage` não acessa o `GraphicsSession` vivo; a UI publica um snapshot novo quando serializa a cena. Isso mantém undo/redo e edição sincronizados e evita corrida de dados entre a thread do QML e a thread de UI.

A URL de preview inclui uma assinatura derivada da geometria, crop, zoom, foco, flip e revisão local do arquivo (tamanho + `mtime_ns`). Se uma foto for sobrescrita no mesmo caminho, o cache do QML recebe uma URL nova.

`ImageInspector.qml` usa `SceneImage.qml` para preview contextual e sempre lê a imagem-fonte original, não a versão já composta pelo provider.

### Reordenação de páginas

`reorder_page` é uma operação transacional do command router. Aceita anterior/próxima, primeira/última ou `target_index`, preserva o ID da página ativa e participa do mesmo undo/redo do restante do documento.

`PageInspector.qml` expõe duas formas de reorganização:

- botões `←` e `→` para movimento determinístico;
- drag-and-drop físico com ghost, indicação da posição alvo e commit transacional no release do mouse.

O conteúdo interno das páginas não é reconstruído durante a troca de ordem.

### Ponte opcional a partir do Studio 5

`studio_bridge.py` prepara um snapshot `.srscene` do `StudioProject` atual e inicia o host Qt em **processo separado**. A ponte fica desligada por padrão e é governada por:

- `graphics_engine_2` — mostra/autoriza o modo experimental;
- `graphics_engine_2_gpu` — usa backend `auto` quando ativo; sem a flag GPU, o modo de teste usa `software`.

Com a flag desligada, o botão do Engine 2 nem é criado no Encartes Studio atual. Com a flag ligada, o shell Turbo mostra `ENGINE 2 · TESTE` ou `ENGINE 2 · GPU`, mantendo o editor antigo aberto como fallback.

Em desenvolvimento, a ponte pode executar `python -m srstudio.graphics2.qt_host`. Em build congelado ela exige um host separado configurado por `SR_GRAPHICS_ENGINE_2_HOST`; se o host ainda não estiver empacotado, a ponte recusa a abertura em vez de tentar executar o Qt dentro do processo Tk.

A camada `compat.py` agora carrega para o snapshot a lista de produtos e os valores vivos de nome, preço dividido, unidade e `image_path`, evitando abrir o Engine 2 com cards semanticamente vazios.

### Caso de referência Quinta Filé

O arquivo real `OFERTAS QUINTA FILÉ NOVO.pptx` foi analisado localmente e não é versionado no repositório. Ele usa as fontes embutidas Anton e High Cruiser, caixas com auto-fit/espaçamento e muitas geometrias customizadas. Esses recursos foram usados para definir o primeiro conjunto de correções da Fase 2.

### Abrir o arquivo real diretamente no Engine 2

O host Qt Quick aceita um arquivo como argumento. Isso permite testar o projeto real sem copiar o PPTX para o repositório:

```bash
sr-graphics-engine-2 "OFERTAS QUINTA FILÉ NOVO.pptx"
```

No Windows é possível forçar o backend do Qt Quick antes da criação da primeira janela:

```bash
sr-graphics-engine-2 "OFERTAS QUINTA FILÉ NOVO.pptx" --graphics-api d3d11
```

Backends expostos pelo host: `auto`, `d3d11`, `d3d12`, `vulkan`, `opengl` e `software`. O padrão é `auto`, preservando a seleção nativa do Qt/plataforma. A barra de status informa o backend resolvido, score do Production Gate e fontes do projeto carregadas.

Pacotes portáteis também podem ser abertos diretamente:

```bash
sr-graphics-engine-2 "quinta-file.srscene" --graphics-api auto
```

Nesse caso, assets e fontes incorporadas são extraídos para cache de runtime e permanecem isolados do sistema operacional.

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
- múltiplas páginas, duplicar e reordenar página;
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

A existência do Studio Bridge **não promove** o Engine 2 automaticamente: o canal estável continua usando o editor antigo enquanto as flags permanecem desligadas.

## Repositório

O motor nasce em `feature/sr-graphics-engine-2` para ficar isolado do canal Beta. Separar em outro repositório pode ser feito depois sem mudar o formato SR Scene 2, pois o pacote foi desenhado como subsistema independente.
