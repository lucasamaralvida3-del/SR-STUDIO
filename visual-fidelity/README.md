# SR Visual Fidelity Lab

Este diretório define o processo de paridade visual do **SR Studio de Encartes / SR Graphics Engine 2**.

## Escopo

O laboratório é exclusivo do Novo Studio de Encartes G2. O Gerador de Cartazes legado é outro produto; seus Golden Masters não são gate de fidelidade nem de Beta do G2.

## Objetivo

O fluxo de referência do Studio é:

1. preservar uma exportação oficial do Canva/PowerPoint;
2. importar o PPTX real no SR Graphics Engine 2;
3. produzir SR Scene 2;
4. renderizar a mesma página pelo `qt_renderer` G2;
5. comparar referência e candidata;
6. gerar diff, heatmap, triage e atribuição;
7. manter fonte e referência imutáveis por SHA-256.

PPTX, PDFs, imagens e fontes reais podem permanecer fora do GitHub. Manifestos, hashes, fingerprints e resultados agregados podem ser versionados.

## Corpus Studio G2 v1 — baseline candidata

Arquivos versionados:

- `g2-studio-corpus-v1.json` — índice hashado e status do corpus;
- `g2-studio-corpus-v1-baseline.json` — primeira distribuição quantitativa;
- `g2-terca-verde-2026-08-11.json` — 3 páginas;
- `g2-quarta-cafe-2026-08-12.json` — 4 páginas;
- `quinta-file-13-08-2026.json` — 4 páginas.

Total atual: **3 documentos / 11 páginas reais do fluxo de encartes G2**.

A baseline foi executada sobre o HEAD funcional `d14dc5bed4bf4f7402f4668eb66a63823f48a35a` e registrou score 94,4183%–97,7681%, média 95,9754% e mediana 96,3717%. Esses valores são baseline de distribuição: **nenhum threshold de outro produto foi herdado como gate oficial do G2**.

### Referência PNG exigida

A regra atual de aprovação exige PNG exportado diretamente do Canva/PowerPoint. As referências oficiais recuperadas nesta rodada são JPEGs diretos do Canva e estão mantidas apenas como baseline candidata hashada. Não converter ou renomear JPEG para fingir conformidade. Uma versão aprovada deverá registrar os PNGs diretos como novos hashes/casos ou nova versão explícita.

### Finding geométrico inicial

11/11 candidates saíram exatamente 1 px mais baixos que as referências. A baseline quantitativa completou/cortou somente o canvas para análise, sem rescale, registrando a dimensão original. Isso é finding visual a ser isolado entre import/page geometry e rounding do renderer, não uma alteração aplicada durante a medição.

### Atribuição inicial

Na passagem granular da baseline candidata, a participação aproximada do gap visual foi:

- LAYERS 53,18%;
- CROP 30,13%;
- MASK 12,45%;
- TEXT 4,23%.

`WORDART`, `PRICE`, `PRODUCT` e `IMPORT` não são isolados como categorias independentes pelo classificador atual; ausência de participação explícita não significa ausência causal.

## Hash validation

`reference_suite` valida SHA-256 do PPTX e SHA/dimensão de cada referência antes da comparação. Um arquivo trocado deve falhar claramente; baselines nunca devem ser atualizadas apenas para conseguir verde.

## Execução

Com o PPTX e referências privadas nos caminhos corretos:

```text
python -m srstudio.graphics2.reference_suite \
  "arquivo.pptx" \
  visual-fidelity/manifesto.json \
  --references visual-fidelity/private/caso \
  --save-scene \
  --out build/golden-master/caso
```

O Reference Suite gera candidate, diff, heatmap, JSON de triage/attribution/impact e fingerprint estrutural. Diferença de dimensão é registrada e deve ser tratada explicitamente.

## Política de thresholds

Nenhum threshold do Gerador de Cartazes ou de outro produto deve ser aplicado automaticamente ao Studio. Primeiro mede-se o corpus G2 real, depois define-se um acceptance policy tecnicamente justificado e versionado. Não relaxar números apenas para conseguir PASS.

## Regra de ouro

Uma referência não é substituída silenciosamente. Nova versão da arte, nova referência ou mudança de formato deve criar novo hash e registro explícito. O objeto sob teste é sempre o G2.
