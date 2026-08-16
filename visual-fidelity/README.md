# SR Visual Fidelity Lab

Este diretório define o processo de paridade visual do SR Graphics Engine 2.0.

## Objetivo

Todo encarte real que já expôs uma falha de importação/renderização deve virar um caso permanente de regressão visual. O fluxo esperado é:

1. preservar uma imagem/PDF de referência exportado do Canva/PowerPoint;
2. importar o projeto no SR Graphics Engine 2;
3. gerar e registrar o fingerprint determinístico da estrutura SR Scene 2;
4. renderizar a mesma página pelo `qt_renderer`;
5. comparar referência e candidata com o Fidelity Lab;
6. bloquear a alteração se o gate estrutural ou visual regredir.

O laboratório mede fidelidade de cor, luminância, bordas/estrutura, proporção de pixels dentro da tolerância, área alterada, erro absoluto e RMS. Diferença de dimensão reprova por padrão.

## Privacidade do corpus real

PPTX, PDF, imagens e fontes extraídas dos projetos reais **não precisam ser versionados no GitHub**. Use `visual-fidelity/local/` ou `visual-fidelity/private/`; ambos estão no `.gitignore`. Relatórios em `build/fidelity/` e `build/golden-master/` também são locais.

O repositório pode manter somente código, manifestos, testes sintéticos e, quando necessário, hashes/fingerprints aprovados. Assim o projeto real do usuário é usado para validação sem ser publicado como fixture.

## Comandos

Comparação direta:

```text
sr-fidelity-lab compare referencia.png candidata.png --name quinta-file --out build/fidelity/quinta-file
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
