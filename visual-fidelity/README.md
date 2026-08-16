# SR Visual Fidelity Lab

Este diretório define o processo de paridade visual do SR Graphics Engine 2.0.

## Objetivo

Todo encarte real que já expôs uma falha de importação/renderização deve virar um caso permanente de regressão visual. O fluxo esperado é:

1. preservar uma imagem de referência exportada do Canva/PowerPoint;
2. importar o projeto no SR Graphics Engine 2;
3. renderizar a mesma página pelo `qt_renderer`;
4. comparar referência e candidata com `sr-fidelity-lab`;
5. bloquear a alteração se o gate visual regredir.

O laboratório mede fidelidade de cor, luminância, bordas/estrutura, proporção de pixels dentro da tolerância, área alterada, erro absoluto e RMS. Diferença de dimensão reprova por padrão.

## Comandos

Comparação direta:

```text
sr-fidelity-lab compare referencia.png candidata.png --name quinta-file --out build/fidelity/quinta-file
```

Executar corpus:

```text
sr-fidelity-lab suite visual-fidelity/manifest.json --out build/fidelity
```

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

Os arquivos pesados de referência podem ser mantidos fora do repositório principal e materializados no CI futuramente. O manifesto permanece a interface estável entre o corpus e o engine.
