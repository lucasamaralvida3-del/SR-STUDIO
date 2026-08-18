# CHAT 8 — Banco Automático de Imagens

## Recovery Audit

- Branch isolada: `g2/parallel-image-database`.
- Worktree solicitado: `../SR-STUDIO-g2-image-database`.
- O runtime atual não expõe um checkout Git local do repositório, portanto `git status`/worktrees não podem ser observados com segurança daqui. A escrita está sendo feita exclusivamente na branch isolada via GitHub connector; nenhuma alteração foi feita em `main`/`stable`.
- `AGENTS.md`, `docs/SR_STUDIO_NEXT_ARCHITECTURE.md` e `docs/G2_CONTINUOUS_PROGRESS.md` foram lidos antes das alterações.
- `docs/G2_CONTINUOUS_PROGRESS.md` permanece somente leitura durante esta missão paralela.
- BASE_SHA: `TO_BE_BACKFILLED_FROM_PARENT_OF_FIRST_CHAT8_COMMIT`.

## Implementação existente auditada

A branch já contém uma base relevante e ela deve ser fortalecida, não recriada:

- `src/srstudio/images/library.py`: persistência, SHA-256, dHash, aliases, review status, preferência e busca.
- `src/srstudio/images/canva_training.py`: treinamento anterior de Canva/PPTX.
- `src/srstudio/images/association.py`: normalização, proteção de gramatura, associação espacial, consenso e classificação decorativa.
- `src/srstudio/images/corpus_training.py`: ingestão incremental por SHA-256 de arquivo, extração via `PptxImporter`, estado com backup e métricas.
- `src/srstudio/images/precision_training.py`: política precision-first e deduplicação lógica de referências repetidas no mesmo slide.
- `src/srstudio/images/lookup.py`: contrato de busca por produto com melhor match, alternativas e confidence.
- `src/srstudio/images/evidence_aliases.py`: aliases aprendidos somente quando compatíveis com identidade/SKU.

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
- `Cartazes Atacarejo SR (1)(2).pptx`;

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

## P0/P1/P2/P3 — baseline

### P0

Nenhum P0 observado na baseline. O estado incremental existente grava backup antes de substituir o state file.

### P1

1. `ImageLibrary.find_near_duplicate()` e `find_cross_product_visual_duplicate()` usam dHash como sinal suficiente. O corpus real revelou uma colisão dHash=0 entre assets visualmente diferentes e de proporções muito diferentes. Isso pode produzir deduplicação/conflito falso.
2. O consenso conta `source_file` pelo basename. Documentos distintos com o mesmo basename podem ser confundidos como uma única origem; por outro lado, cópias idênticas com nomes diferentes não devem aumentar consenso. O SHA-256 do documento precisa ser a identidade de origem.
3. Corpus de template sem foto de produto deve terminar com 0 associações Produto ↔ Imagem, e não ser empurrado para `accepted` por proximidade de logo/fundo.

### P2

- Separar formalmente `naming/layout corpus` de `product-image corpus` para reduzir revisão inútil.
- Ingestão opcional das imagens individuais da Library com provenance explícito.

### P3

- Estatísticas adicionais de colisões perceptuais e cobertura por categoria.
- Interface de revisão dedicada.

## Próximos ciclos

1. Endurecer deduplicação perceptual com gate de geometria/aspect ratio e testes de colisão dHash.
2. Usar SHA-256 do documento como identidade de origem do consenso.
3. Adicionar testes em que corpus real de template produz zero auto-accepted product images.
4. Criar inventário reexecutável que distingue `product-image`, `decorative/branding` e `naming-only`.
5. Integrar imagens standalone somente como fonte suplementar, mantendo provenance.
6. Executar consultas reais no `find_image()` quando existirem assets aprovados para os SKUs do corpus.

## Fronteiras com outros chats

- CHAT 2: este trabalho consome `PptxImporter`; não refatora o importador.
- CHAT 4: apenas expõe/fortalece contrato de lookup; não altera ProductCards/bindings.
- CHAT 5: testes e métricas produzidos aqui podem ser consumidos por QA.

## Commits

- primeiro commit desta documentação: ver histórico da branch; BASE_SHA será preenchido com o parent desse commit no próximo checkpoint.
