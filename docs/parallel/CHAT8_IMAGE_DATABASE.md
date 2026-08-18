# CHAT 8 — Banco Automático de Imagens

## Recovery Audit

- Branch isolada: `g2/parallel-image-database`.
- Worktree solicitado: `../SR-STUDIO-g2-image-database`.
- O runtime atual não expõe um checkout Git local do repositório, portanto `git status`/worktrees não podem ser observados com segurança daqui. A escrita está sendo feita exclusivamente na branch isolada via GitHub connector; nenhuma alteração foi feita em `main`/`stable`.
- `AGENTS.md`, `docs/SR_STUDIO_NEXT_ARCHITECTURE.md` e `docs/G2_CONTINUOUS_PROGRESS.md` foram lidos antes das alterações.
- `docs/G2_CONTINUOUS_PROGRESS.md` permanece somente leitura durante esta missão paralela.
- BASE_SHA: `3b44feaf6480e286d3619d0a1c0c00a13a4f450c`.

## Implementação existente auditada

A branch já contém uma base relevante e ela deve ser fortalecida, não recriada:

- `src/srstudio/images/library.py`: persistência, SHA-256, dHash, aliases, review status, preferência e busca.
- `src/srstudio/images/canva_training.py`: treinamento anterior de Canva/PPTX.
- `src/srstudio/images/association.py`: normalização, proteção de gramatura, associação espacial, consenso e classificação decorativa.
- `src/srstudio/images/corpus_training.py`: ingestão incremental por SHA-256 de arquivo, extração via `PptxImporter`, estado com backup e métricas.
- `src/srstudio/images/precision_training.py`: política precision-first e deduplicação lógica de referências repetidas no mesmo slide.
- `src/srstudio/images/lookup.py`: contrato de busca por produto com melhor match, alternativas e confidence.
- `src/srstudio/images/evidence_aliases.py`: aliases aprendidos somente quando compatíveis com identidade/SKU.
- `src/srstudio/images/safe_library.py`: persistência fail-closed com backup lógico; agora também aplica deduplicação perceptual conservadora.

## Inventário do corpus real acessível — baseline 2026-08-18

### PPTX

A biblioteca acessível lista 19 PPTX. Quatro estão marcados como artefatos gerados pelo modelo e não são usados como verdade de treinamento. Foram materializados 15 PPTX originais/operacionais do SR para auditoria estrutural.

Baseline dos 15 PPTX materializados:

- arquivos: 15;
- arquivos únicos por SHA-256: 13;
- slides: 295;
- arquivos de mídia internos (ocorrências por pacote): 43;
- referências de imagem em shapes/slides: 363;
- imagens únicas exatas por SHA-256: 14;
- ocorrências exatas duplicadas entre os pacotes: 29;
- pares near-duplicate encontrados com dHash <= 4 e SHA diferente: 1;
- esse único par tinha dHash idêntico mas imagens visualmente diferentes, demonstrando colisão perceptual e confirmando que dHash isolado não pode autorizar merge.

Duplicata de arquivo confirmada:

- `Cartazes Atacarejo SR (1).pptx`;
- `Cartazes Atacarejo SR (1)(1).pptx`;
- `Cartazes Atacarejo SR (1)(2).pptx`.

Os três possuem o mesmo SHA-256 de arquivo e devem ser processados uma única vez pelo fluxo incremental.

### Característica importante do corpus PPTX

`Cartazes Atacarejo SR (1).pptx` possui 93 slides e texto estruturado real, mas apenas 1 mídia reutilizada em todos os slides. Portanto ele é valioso para nomenclatura, preço e layout, porém não é uma fonte de fotografias de produto.

`OFERTAS QUINTA FILÉ NOVO.pptx` possui 3 slides, 9 mídias internas e 31 referências. A inspeção de todas as mídias mostrou fundos, selo Quinta Filé, logo SR, marca Smart, logo Adeel, gradientes e elementos de template — não fotos de SKU. Esses assets devem ser classificados como `decorative/branding`, nunca como Produto ↔ Imagem.

A inspeção visual das 14 mídias únicas dos PPTX materializados mostrou somente branding/template/decorativos. Assim, a baseline correta de fotos de produto extraíveis desses PPTX específicos é 0; forçar associações produziria P1 de precisão.

### PDFs correlatos

Foram auditados `atacado.PDF`, `atacado(1).PDF` e `ATACADO INICIO.PDF`:

- 26 páginas cada;
- texto/vetor estruturado;
- zero imagens raster embutidas.

`CUSTO.PDF` possui 616 páginas e também não expõe imagens raster de produto.

`SR_STUDIO_PROMOCOES.pdf` possui 7 páginas e imagens raster, mas a inspeção visual mostra principalmente logos/QR/elementos de cartaz; não deve ser tratado automaticamente como corpus de fotos de SKU.

### Imagens individuais suplementares já disponíveis na biblioteca

A biblioteca contém assets de produtos enviados/criados anteriormente, incluindo exemplos como:

- amaciante Smart 2L;
- pão de queijo Rodrigues;
- feijão Paraná 1kg;
- papel higiênico;
- hambúrguer em embalagem;
- farinha artesanal;
- outros produtos fotografados/recortados.

Esses arquivos são uma fonte suplementar útil, porém devem entrar com provenance `standalone-library` e sem fingir que foram aprendidos de um PPTX.

## Produtos/textos reais observados

Entre os nomes estruturados já encontrados no corpus estão, por exemplo:

- `MONSTER 473ML`;
- `EXTRATO ELEFANTE 300G`;
- `FEIJÃO PRETO DU BOM 1KG`;
- `FEIJÃO VERMELHO PINK 1KG`;
- `FEIJÃO CARIOCA DU BOM 1KG`;
- `SPRITE ORIGINAL PET 2L`;
- `SAB PROTEX 85G`;
- `MARGARINA QUALY TK 1KG`;
- `COXA SOBRECOXA DESOSSADA PERDIGÃO 1KG`;
- `BATATA BEM BRASIL CANOA 1,05KG`;
- `HAMBÚRGUER SADIA ANGUS 360G`;
- `PÃO DE QUEIJO CONGELADO SR 1KG`.

O corpus de cartazes deve alimentar normalização/aliases/produtos mesmo quando não contém foto embutida, mas não deve gerar associação Produto ↔ Imagem sem evidência visual.

## Melhorias implementadas nesta missão

### Consenso por identidade real do documento

`association.py` deixou de usar apenas o basename em `distinct_source_count`. A identidade de origem agora segue esta prioridade:

1. `metadata.source_document_id`/`metadata.source_sha256` quando disponível;
2. digest presente no caminho de extração `.../media/<source-sha-prefix>/...`;
3. fallback para `source_file` por compatibilidade.

Consequências:

- cópias idênticas renomeadas não aumentam artificialmente a confiança;
- documentos realmente diferentes com o mesmo nome continuam contando como fontes distintas;
- o comportamento antigo continua compatível para evidências sintéticas/legadas sem digest.

### Deduplicação perceptual conservadora

Foi criado `src/srstudio/images/visual_dedup.py`.

SHA-256 continua sendo a única identidade exata. dHash é usado apenas como candidato perceptual e agora precisa concordar também com:

- orientação;
- aspect ratio dentro de tolerância conservadora.

`SafeImageLibrary` sobrescreve `find_near_duplicate()` e `find_cross_product_visual_duplicate()` com esse gate. O caso real observado no corpus — dHash 0 para uma imagem 119×119 e outra 2160×933 — deixa de ser merge/conflito falso.

### Pipeline em lote reexecutável

Foi criado `src/srstudio/images/batch_training.py` com uma entrada executável:

```text
python -m srstudio.images.batch_training --library <bank> --imports-root <imports> [--report report.json] [--query "MONSTER 473ML"] <corpus...>
```

Fluxo:

`PPTX/ZIP/DIRETÓRIO → INVENTÁRIO → EXTRAÇÃO ESTRUTURADA → HASH → FILTRO DE TEMPLATE → ASSOCIAÇÃO ESPACIAL → CONSENSO → CONFIDENCE → SAFE IMAGE LIBRARY → ALIASES → LOOKUP → RELATÓRIO JSON`

O processamento continua incremental pelo SHA-256 do arquivo e usa `PrecisionProductImageCorpusTrainer` + `SafeImageLibrary`.

## P0/P1/P2/P3 — estado atual

### P0

Nenhum P0 observado. `CorpusStateStore` e `SafeImageLibrary` preservam backup lógico e falham fechados em caso de JSON corrompido.

### P1

1. **MITIGADO NO CAMINHO SEGURO** — colisão dHash: `SafeImageLibrary` agora exige geometria compatível além do hash perceptual.
2. **CORRIGIDO** — consenso por basename: usa identidade de conteúdo/documento quando disponível.
3. **ABERTO** — corpus de template curto pode produzir candidatos `review` de logo/fundo; eles não devem chegar a lookup aprovado. É necessário continuar reduzindo o volume de revisão sem perder produtos legítimos.
4. **INTEGRAÇÃO NECESSÁRIA** — `src/srstudio/app/professional.py` ainda instancia `ImageLibrary` diretamente. Para levar a proteção perceptual ao Studio principal sem refatorar o shell, a alteração mínima futura é trocar a construção para `SafeImageLibrary`. O batch novo já usa a biblioteca segura.

### P2

- Separar formalmente `naming/layout corpus` de `product-image corpus` para reduzir revisão inútil.
- Ingestão opcional das imagens individuais da Library com provenance explícito.
- Medir latência de consulta com corpus real maior.

### P3

- Estatísticas adicionais de colisões perceptuais e cobertura por categoria.
- Interface de revisão dedicada.

## Testes adicionados

- `tests/test_image_association.py`
  - mesmo basename + documentos diferentes;
  - cópias exatas renomeadas não contam como fontes novas;
  - `source_sha256` explícito tem prioridade.
- `tests/test_image_visual_dedup.py`
  - colisão realista de dHash com geometria incompatível;
  - resize de mesma proporção continua candidato near-duplicate;
  - biblioteca segura não mescla nem cria conflito falso nesses casos.
- `tests/test_image_batch_training.py`
  - contrato do processamento em lote;
  - relatório JSON reconstruível.

O ambiente desta sessão não possui checkout local do repositório e não disparou workflows de CI para os commits diretos da branch; portanto a execução completa do `pytest` ainda precisa ser feita no worktree/CI que possui o código. Nenhum resultado de teste foi inventado.

## Fronteiras com outros chats

- CHAT 2: este trabalho consome `PptxImporter`; não refatora o importador.
- CHAT 4: apenas expõe/fortalece contrato de lookup; não altera ProductCards/bindings.
- CHAT 5: testes e métricas produzidos aqui podem ser consumidos por QA.
- Integração futura mínima no shell: `src/srstudio/app/professional.py` deve construir `SafeImageLibrary` no lugar de `ImageLibrary`; não é necessário alterar o contrato de `ImageBankView`.

## Próximos ciclos

1. Reduzir falsos candidatos `review` de branding/template em decks curtos.
2. Produzir inventário reexecutável que classifique fonte como `product-image`, `decorative/branding` ou `naming-only`.
3. Adicionar ingestão de standalone assets com provenance explícito e confidence conservador.
4. Validar lookup real com SKUs que efetivamente possuam imagem aprovada no corpus.
5. Medir ingestão/hash/indexação/lookup em volume maior.
6. Executar a suíte no worktree/CI e corrigir qualquer regressão encontrada.

## Commits CHAT 8 desta sessão

- `721ec2667c65fc9862a132d62e00dd094b94d0d1` — recovery audit + baseline do corpus.
- `8a204a5ae0fd8d456645f601071480a6904e7407` — consenso source-content-aware.
- `2ed879feeab2e58ef275e37cdf4b3c34a8eb4ce2` — testes do consenso por identidade de documento.
- `da8da265c2e99cd491d701a2f25f45f89c0569b6` — gate perceptual conservador.
- `fe62b485f241e777024826c34c176ab0aeec7aaa` — dedupe segura em `SafeImageLibrary`.
- `41ffb0552f63e5daf0ca3b348dc0ebf95008ec52` — testes de colisão dHash.
- `a658a407e2c5967a8ceb7a248da0951624ae3036` — comando de treinamento em lote.
- `97ded045b5f24b3a2a576317f274447671b3b517` — teste do contrato batch/report.
