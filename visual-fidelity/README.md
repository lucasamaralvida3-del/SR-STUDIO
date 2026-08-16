# SR Visual Fidelity Lab

Este diretório define o processo de paridade visual do SR Graphics Engine 2.0.

## Objetivo

Todo encarte real que já expôs uma falha de importação/renderização deve virar um caso permanente de regressão visual. O fluxo esperado é:

1. preservar uma imagem/PDF de referência exportado do Canva/PowerPoint;
2. importar o projeto no SR Graphics Engine 2;
3. gerar e registrar o fingerprint determinístico da estrutura SR Scene 2;
4. renderizar a mesma página pelo `qt_renderer`;
5. comparar referência e candidata com o Fidelity Lab;
6. localizar automaticamente as regiões de maior divergência com o Fidelity Triage;
7. bloquear a alteração se o gate estrutural ou visual regredir.

O laboratório mede fidelidade de cor, luminância, bordas/estrutura, proporção de pixels dentro da tolerância, área alterada, erro absoluto e RMS. Diferença de dimensão reprova por padrão.

A partir da `2.0.0-alpha.25`, o **Fidelity Triage** complementa o score global com análise espacial. A página é dividida em tiles, regiões adjacentes são agrupadas e ordenadas por impacto (`pixels alterados × erro médio`). Isso permite atacar primeiro a área que mais derruba a fidelidade — por exemplo preço composto, nome, crop do produto ou fundo — em vez de corrigir a página inteira no escuro.

## Privacidade do corpus real

PPTX, PDF, imagens e fontes extraídas dos projetos reais **não precisam ser versionados no GitHub**. Use `visual-fidelity/local/` ou `visual-fidelity/private/`; ambos estão no `.gitignore`. Relatórios em `build/fidelity/` e `build/golden-master/` também são locais.

O repositório pode manter somente código, manifestos, testes sintéticos e, quando necessário, hashes/fingerprints aprovados. Assim o projeto real do usuário é usado para validação sem ser publicado como fixture.

## Quinta Filé — Golden Master real

O caso `visual-fidelity/quinta-file-13-08-2026.json` registra o PPTX real pelo SHA-256 e associa as quatro exportações oficiais recebidas do Canva aos slides exatos do arquivo fonte:

- slide 12 — grade Acém/Frango/Costela/Bacon/Picanha;
- slide 13 — Costelinha/Linguiça Calabresa;
- slide 14 — grade Frango Caipira/Linguiça/Mocotó/Almôndega/Salsicha;
- slide 15 — destaque Linguiça Mista Caseira SR.

As imagens continuam fora do GitHub. O manifesto guarda nome, dimensão e SHA-256 de cada exportação para impedir que uma imagem errada seja aceita silenciosamente como baseline.

A auditoria OOXML das **quatro páginas oficiais** do PPTX hashado já mede o contrato estrutural que o Engine precisa preservar antes mesmo do score visual: **347 shapes, 157 caixas de texto, 71 imagens `p:sp + a:blipFill`, 71 `stretch/fillRect`, 18 fillRects com outset negativo, 29 máscaras `custGeom` irregulares, 54 grupos e aproximadamente 29 preços compostos**. Não há `p:pic` nessas páginas. `custGeom` retangular equivalente à própria caixa é tratado como geometria trivial e não cria um falso requisito de máscara; somente as 29 formas realmente irregulares entram no `image_clip_coverage` do Production Gate.

Isso é especialmente relevante para a Quinta Filé porque o Canva usa `fillRect` negativo para estender a fotografia além da caixa antes do recorte. Um exemplo real do arquivo usa `l=-30959` e `r=-30437` (unidades OOXML), fazendo o BLIP ocupar aproximadamente **161,396% da largura da forma**. O G2 alpha.27 preserva esse contrato no import, preview Qt Quick e renderer QPainter em vez de cair no `cover` genérico.

Para executar o conjunto real após colocar as quatro imagens em uma pasta local:

```text
python -m srstudio.graphics2.reference_suite \
  "OFERTAS QUINTA FILÉ NOVO (1).pptx" \
  visual-fidelity/quinta-file-13-08-2026.json \
  --references visual-fidelity/private/quinta-file-13-08-2026 \
  --save-scene \
  --out build/golden-master/quinta-file-13-08-2026
```

Esse modo é propositalmente **esparso**: o PPTX pode conter dezenas de slides históricos, mas somente as páginas que possuem exportação oficial são usadas no gate visual. Cada referência aponta explicitamente para o índice zero-based da página importada.

O Reference Suite agora produz, por página, três artefatos complementares: imagem `diff`, heatmap espacial e JSON de triagem. O relatório principal incorpora as regiões ordenadas por impacto e o console informa a maior região divergente (`x/y/largura/altura`). Portanto, quando a Quinta Filé real for executada, o primeiro ajuste do renderer será escolhido pelo pior caso **medido**, não por estimativa visual.

## Comandos

Comparação direta:

```text
sr-fidelity-lab compare referencia.png candidata.png --name quinta-file --out build/fidelity/quinta-file
```

Triagem espacial de uma comparação já renderizada:

```text
python -m srstudio.graphics2.fidelity_triage \
  referencia.png candidata.png \
  --pixel-tolerance 12 \
  --out build/fidelity/triage.json \
  --heatmap build/fidelity/triage-heatmap.png
```

Executar corpus:

```text
sr-fidelity-lab suite visual-fidelity/manifest.json --out build/fidelity
```

Auditar um PPTX real sem referência visual:

```text
sr-fidelity-lab pptx-audit "OFERTAS QUINTA FILÉ NOVO.pptx" --save-scene --out build/fidelity/quinta-file
```

Comparar uma única página do PPTX com PNG de referência:

```text
sr-fidelity-lab pptx-render-compare "OFERTAS QUINTA FILÉ NOVO.pptx" pagina-1.png --page 0 --save-scene
```

Golden Master multipágina contra o PDF oficial:

```text
sr-pptx-golden-master "OFERTAS QUINTA FILÉ NOVO.pptx" "OFERTAS QUINTA FILÉ NOVO.pdf" \
  --target-width 2160 \
  --save-scene \
  --out build/golden-master/quinta-file
```

O Golden Master compara todas as páginas e usa **o pior score visual**, não a média, no Production Gate. A quantidade de páginas também deve ser idêntica. O relatório inclui o fingerprint estrutural do SR Scene 2 para detectar drift mesmo quando IDs de runtime e caminhos de cache mudam.

Renderizar um pacote SR Scene e comparar com uma referência (requer o extra `graphics2` / PySide6):

```text
sr-fidelity-lab render-compare projeto.srscene referencia.png --name quinta-file --dpi 300 --out build/fidelity/quinta-file
```

## Política

A política inicial é propositalmente exigente, mas tolera pequenas diferenças de antialiasing entre ambientes:

- score mínimo: `98.5%`;
- pixels dentro da tolerância: `96.5%`;
- tolerância por canal: `12/255`;
- área máxima alterada: `3.5%`;
- tamanho da imagem: deve ser idêntico.

Casos críticos podem usar limites mais altos por projeto. O objetivo final para os modelos oficiais SR é elevar gradualmente o score para `99.x%` sem mascarar regressões.

O Triage usa a mesma tolerância de pixel do caso visual. A prioridade de uma região não altera o resultado PASS/FAIL: ela serve apenas para decidir a ordem de correção. O gate continua sendo definido pelas métricas globais e pelo pior caso real.

## Regra de ouro

Uma baseline nunca deve ser atualizada apenas para fazer o teste passar. Primeiro deve ser demonstrado que a mudança visual é intencional e correta. Caso contrário, a baseline antiga permanece e o engine deve ser corrigido.

## Corpus real

O primeiro lote deve incluir, no mínimo:

- Quinta Filé que apresentou sobreposição de nomes/preços/imagens;
- encarte com preço de 1 dígito, 2 dígitos e 3 dígitos;
- encarte com `/KG` e `/UN`;
- encarte com limite por CPF;
- modelo com preço APP;
- modelo de atacado com varejo, atacado e quantidade;
- projeto com múltiplas páginas;
- projeto Canva/PPTX com fontes não instaladas;
- projeto com crop, rotação, transparência, sombras, grupos e camadas.

Os arquivos pesados de referência ficam fora do repositório principal. O manifesto, os hashes e os fingerprints permanecem como interfaces estáveis entre o corpus e o engine.
