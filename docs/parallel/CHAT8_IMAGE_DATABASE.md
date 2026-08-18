# CHAT 8 — Banco Automático de Imagens

## Recovery Audit

- Branch isolada: `g2/parallel-image-database`.
- Worktree solicitado: `../SR-STUDIO-g2-image-database`.
- O runtime desta sessão não expõe um checkout Git local do repositório, portanto `git status` e a lista de worktrees locais não puderam ser observados diretamente. As alterações desta sessão foram escritas exclusivamente na branch isolada via GitHub connector.
- Nenhuma alteração foi feita em `main` ou `stable`.
- `AGENTS.md`, `docs/SR_STUDIO_NEXT_ARCHITECTURE.md` e `docs/G2_CONTINUOUS_PROGRESS.md` foram lidos antes das alterações.
- `docs/G2_CONTINUOUS_PROGRESS.md` permaneceu somente leitura.
- BASE_SHA: `3b44feaf6480e286d3619d0a1c0c00a13a4f450c`.

## Implementação existente auditada

A branch já possuía uma base relevante e foi fortalecida em vez de recriada:

- `src/srstudio/images/library.py`: persistência, hash, aliases, review status, preferência e busca.
- `src/srstudio/images/canva_training.py`: treinamento Canva/PPTX anterior.
- `src/srstudio/images/association.py`: normalização, proteção de gramatura, associação espacial, consenso e classificação decorativa.
- `src/srstudio/images/corpus_training.py`: ingestão incremental por SHA-256, extração via `PptxImporter`, estado com backup e métricas.
- `src/srstudio/images/precision_training.py`: política precision-first.
- `src/srstudio/images/lookup.py`: contrato `find_image()` com best match, alternativas e confidence.
- `src/srstudio/images/evidence_aliases.py`: aliases baseados em evidência e compatibilidade de SKU.
- `src/srstudio/images/safe_library.py`: persistência fail-closed e biblioteca segura.
- `src/srstudio/products/database.py` e `src/srstudio/products/sync.py`: consultados; nenhuma refatoração grande foi feita para não invadir o CHAT 4.

## Corpus real acessível — baseline estrutural 2026-08-18

A Library acessível contém 19 PPTX. Quatro estão marcados como artefatos gerados pelo modelo e não foram usados como verdade de treinamento. Foram materializados e auditados 15 PPTX originais/operacionais do SR.

### Métricas dos 15 PPTX

- arquivos encontrados: **15**;
- arquivos únicos exatos por SHA-256: **13**;
- documentos lógicos únicos: **11**;
- slides: **295**;
- referências de imagem em shapes/slides: **363**;
- mídias internas, somadas por pacote: **43**;
- imagens únicas exatas por SHA-256: **14**;
- ocorrências de texto candidato a produto: **545**;
- produtos normalizados únicos observados: **124**;
- decks `text-only`: **1**;
- decks `template-heavy`: **5**;
- decks `mixed`: **9**;
- grupos de arquivos exatamente duplicados: **1**;
- grupos adicionais de exportações logicamente duplicadas: **2**;
- pares de mídia com dHash <= 4 e SHA diferente: **1**;
- pares perceptuais rejeitados pelo gate de geometria: **1**.

A auditoria estrutural equivalente executada localmente sobre os 15 PPTX levou aproximadamente **0,88–0,92 s** em três execuções. Esse número mede o inventário ZIP/XML/PIL no ambiente desta sessão, não a suíte completa do SR Studio.

### Duplicatas exatas

Os três arquivos abaixo são byte a byte equivalentes pelo SHA-256 do PPTX:

- `Cartazes Atacarejo SR (1).pptx`;
- `Cartazes Atacarejo SR (1)(1).pptx`;
- `Cartazes Atacarejo SR (1)(2).pptx`.

Eles devem representar uma única fonte documental para consenso.

### Exportações logicamente duplicadas

Foram encontrados dois grupos em que o SHA do arquivo muda, mas o conteúdo útil de slides/textos/mídias é equivalente:

1. `OFERTAS QUINTA FILÉ NOVO.pptx` ↔ `OFERTAS QUINTA FILÉ NOVO(1).pptx`;
2. `SEGUNDA DA LIMPEZA 2 PRECO.pptx` ↔ `SEGUNDA DA LIMPEZA 2 PRECO COM LIMITE.pptx` no conteúdo estrutural relevante ao Produto↔Imagem disponível no pacote.

O consenso agora possui identidade lógica de documento para que exportações equivalentes não aumentem confiança artificialmente.

### Característica decisiva do corpus atual

`Cartazes Atacarejo SR (1).pptx` possui 93 slides e muitos nomes de produtos reais, mas apenas **1 mídia reutilizada nas 93 páginas**. Ele é excelente corpus de nomenclatura/layout, porém não contém uma foto diferente de produto por slide.

`OFERTAS QUINTA FILÉ NOVO.pptx` possui 3 slides, 9 mídias internas e 31 referências de imagem. A inspeção visual das mídias mostrou fundo, selo Quinta Filé, logo SR, Smart, Adeel, gradientes e elementos promocionais — não fotos das embalagens/SKUs.

A inspeção visual das **14 mídias únicas** de todos os PPTX materializados mostrou branding/template/decorativos. A baseline correta de **fotos de produto extraíveis desses PPTX específicos é 0**. O sistema não deve fabricar associações para aumentar cobertura.

## PDFs correlatos

Foram auditados:

- `atacado.PDF` — 26 páginas;
- `atacado(1).PDF` — 26 páginas;
- `ATACADO INICIO.PDF` — 26 páginas;
- `CUSTO.PDF` — 616 páginas;
- `SR_STUDIO_PROMOCOES.pdf` — 7 páginas.

Os três PDFs de atacado e `CUSTO.PDF` não expõem imagens raster de produto; são predominantemente texto/vetor. `SR_STUDIO_PROMOCOES.pdf` contém raster, mas a inspeção mostra principalmente logos/QR/elementos do cartaz. PDFs permanecem úteis como referência visual/layout, não como substituto automático do asset original.

## Imagens standalone disponíveis na Library

A Library também contém imagens individuais de produtos enviados/criados anteriormente, por exemplo:

- amaciante Smart 2L;
- pão de queijo Rodrigues;
- feijão Paraná 1kg;
- papel higiênico;
- hambúrguer em embalagem;
- mandioca congelada;
- farinha artesanal;
- outros produtos recortados/fotografados.

Esses arquivos podem alimentar uma segunda fonte de conhecimento com provenance explícito `standalone-library`. Eles não devem ser registrados como se tivessem sido aprendidos de PPTX e o nome do arquivo, sozinho, não deve autorizar um auto-accept inseguro.

## Produtos reais observados no corpus

Exemplos estruturados já encontrados:

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
- `ASA DE FRANGO SADIA BANDEJA 1KG`;
- `COXINHA DA ASA SADIA BANDEJA 1KG`;
- `HAMBÚRGUER SADIA ANGUS 360G`;
- `PÃO DE QUEIJO CONGELADO SR 1KG`.

O corpus de cartazes alimenta normalização/nomenclatura mesmo quando não contém foto. Isso é separado da evidência necessária para Produto↔Imagem.

## Melhorias implementadas

### 1. Consenso por identidade real/lógica do documento

`association.py` não usa mais apenas o basename como `distinct_source_count`.

Prioridade de identidade:

1. `metadata.source_document_id`;
2. `metadata.source_sha256`;
3. digest reconhecido no caminho `.../media/<digest>/...`;
4. `source_file` como fallback compatível.

`PrecisionProductImageCorpusTrainer` agora cria `source_document_id` conservador usando:

- quantidade de slides;
- quantidade de referências de mídia;
- conjunto de SHA-256 das mídias;
- nomes normalizados dos produtos;
- pares `(slide, produto, image_sha256)`.

Assim:

- cópias exatas renomeadas não votam várias vezes;
- exportações logicamente equivalentes também não votam várias vezes;
- documentos realmente diferentes com o mesmo basename continuam independentes.

### 2. Versionamento incremental da política de precisão

`PRECISION_TRAINER_VERSION = g2-image-precision-v2`.

Records antigos sem a versão atual são reprocessados quando aquela fonte entra novamente no batch, sem transformar a atualização de algoritmo em reprocessamento global desnecessário.

### 3. Deduplicação perceptual conservadora

Foi criado `src/srstudio/images/visual_dedup.py`.

SHA-256 permanece a identidade exata. dHash serve somente para levantar candidatos near-duplicate e precisa concordar também com:

- orientação;
- aspect ratio dentro de tolerância conservadora.

O caso real encontrado no corpus tinha:

- dHash: idêntico;
- distância de Hamming: 0;
- imagem A: 119×119;
- imagem B: 2160×933;
- diferença relativa de aspect ratio: ~56,8%.

Essas imagens visualmente diferentes agora são rejeitadas como duplicata.

### 4. SHA-256 completo + provenance sem migração destrutiva

O ID legado de `ImageLibrary` permanece compatível com 24 caracteres. `SafeImageLibrary` passou a preservar também o SHA-256 completo em metadata:

- `sha256`;
- `sha256_full`.

Ao consolidar uma near-duplicate recomprimida:

- o SHA canônico não é trocado silenciosamente;
- novos hashes exatos vão para `variant_sha256`;
- provenance anterior e nova são unidas e deduplicadas.

### 5. Aliases também funcionam em variantes visuais canônicas

`evidence_aliases.py` aceita evidência da imagem canônica ou de um hash conhecido em `variant_sha256`, mantendo a proteção contra gramaturas/SKUs diferentes.

### 6. Template/branding com conflito vira decorativo mais cedo

O consenso agora usa `metadata.template_asset`.

Uma mídia recorrente marcada como template, observada em pelo menos 3 associações e ligada a pelo menos 3 produtos diferentes com baixo consenso, é classificada `decorative` sem precisar contaminar uma fila enorme de revisão.

Uma imagem repetida em vários documentos para o **mesmo produto** continua apta a aumentar confiança.

### 7. Inventário estrutural reexecutável

Foi criado `src/srstudio/images/corpus_inventory.py`.

Ele lê o pacote PPTX diretamente, sem OCR e sem screenshot, e produz:

- SHA-256 do arquivo;
- identidade lógica do documento;
- slides;
- textos estruturados;
- referências `a:blip`, inclusive imagens usadas como fill de shape;
- mídia original do pacote;
- SHA-256 completo da mídia;
- dimensões, MIME e dHash;
- recorrência/template;
- produtos normalizados;
- duplicatas exatas;
- duplicatas lógicas;
- near-duplicates;
- colisões dHash rejeitadas pela geometria;
- classificação `text-only`, `template-heavy` ou `mixed`.

O near-duplicate inventory usa BK-tree de Hamming em vez de comparar toda imagem com toda imagem.

Comando independente:

```text
python -m srstudio.images.corpus_inventory --report corpus.json <PPTX/DIRETÓRIO...>
```

### 8. Batch completo INVENTÁRIO → BANCO

`src/srstudio/images/batch_training.py` agora executa:

```text
INVENTÁRIO
→ EXTRAÇÃO ESTRUTURADA
→ SHA-256
→ FILTRO DE TEMPLATE
→ ASSOCIAÇÃO ESPACIAL
→ CONSENSO
→ CONFIDENCE
→ SAFE IMAGE LIBRARY
→ ALIASES
→ LOOKUP
→ RELATÓRIO JSON
```

Exemplo:

```text
python -m srstudio.images.batch_training \
  --library <bank> \
  --imports-root <imports> \
  --report image-db-report.json \
  --query "MONSTER 473ML" \
  <corpus...>
```

O relatório contém inventário, métricas de treino, decisões, ambiguidades, provenance, aliases e resultados de lookup.

## API futura para ProductCards

Já existe o contrato sem invadir o CHAT 4:

```python
result = find_image(library, product_name, alternatives=3)
```

Resultado conceitual:

- `best_match`;
- `alternatives`;
- `confidence`.

O lookup usa somente assets `accepted`, protege gramatura/volume e usa índice de tokens para limitar candidatos fuzzy.

## P0/P1/P2/P3 — estado atual

### P0

Nenhum P0 conhecido no caminho seguro.

- `CorpusStateStore` falha fechado se o JSON estiver corrompido e mantém `.bak`;
- `SafeImageLibrary` valida antes de sobrescrever e mantém backup lógico;
- nenhuma migração destrutiva do ID legado foi feita.

### P1

1. **MITIGADO NO CAMINHO SEGURO** — dHash isolado poderia fundir imagens erradas; `SafeImageLibrary` agora exige geometria compatível.
2. **CORRIGIDO** — consenso por basename podia superestimar cópias; agora usa identidade documental/lógica.
3. **MITIGADO** — assets recorrentes de template em decks curtos agora podem ser classificados `decorative` com 3 produtos conflitantes.
4. **ABERTO / INTEGRAÇÃO** — `src/srstudio/app/professional.py`, método `_attach_project`, ainda instancia `ImageLibrary` diretamente. A alteração mínima solicitada ao ponto de integração é usar `SafeImageLibrary(self.data_dir / "images")`. O batch desta branch já usa `SafeImageLibrary`.
5. **ABERTO POR DADO, NÃO POR ALGORITMO** — os 15 PPTX reais materializados não contêm fotos de SKU. A biblioteca não deve marcar branding como produto apenas para parecer preenchida.

### P2

- criar ingestão conservadora de imagens standalone com provenance `standalone-library` e correspondência com catálogo;
- medir o lookup com banco real populado, além do teste sintético existente com 5.000 assets;
- separar ainda mais explicitamente `naming/layout corpus` de `product-image corpus` na UI/relatório.

### P3

- interface dedicada de revisão ambígua;
- estatísticas de cobertura por categoria/marca;
- ranking visual adicional para múltiplas fotos válidas do mesmo SKU.

## Testes adicionados/fortalecidos

### `tests/test_image_association.py`

- normalização e gramatura;
- mesmo basename com documentos diferentes;
- cópias exatas renomeadas não contam como fontes novas;
- identidade documental explícita;
- asset global ligado a vários produtos vira decorativo;
- template recorrente com 3 produtos diferentes vira decorativo;
- repetição do mesmo SKU não é rejeitada.

### `tests/test_image_visual_dedup.py`

- colisão dHash com geometria incompatível;
- resize de mesma proporção continua candidato near-duplicate;
- SHA-256 completo é preservado;
- ID legado continua compatível;
- PNG/JPEG near-duplicate mantém SHA canônico;
- `variant_sha256` é registrado;
- provenance de origens diferentes é unida;
- colisão cross-product não gera conflito falso.

### `tests/test_image_evidence_aliases.py`

- alias equivalente;
- gramatura diferente rejeitada;
- alias de variante visual canônica;
- SHA sem relação rejeitado.

### `tests/test_image_precision_training.py`

- shapes repetidos com mesmo SHA viram uma imagem lógica;
- singleton fraco não cruza auto-accept;
- fingerprint lógico colapsa export copies;
- fingerprint muda se Produto↔Imagem muda;
- record preserva raw SHA + logical source ID;
- record de versão de precisão antiga é reprocessado incrementalmente.

### `tests/test_image_corpus_inventory.py`

- texto estruturado + image fill;
- arquivo exatamente duplicado;
- export copy logicamente igual com bytes diferentes;
- deck template-heavy;
- colisão dHash 0 rejeitada por geometria;
- fonte ausente gera warning não destrutivo.

### `tests/test_image_batch_training.py`

- inventário vem antes do treino;
- uso da biblioteca segura;
- relatório JSON contém inventário + métricas + decisões/lookup.

O ambiente desta sessão não possui checkout local do repositório e não disparou workflow CI para os commits diretos da branch. Portanto os testes acima foram adicionados, mas a suíte `pytest` do repositório **não foi declarada como executada com sucesso**. Nenhum resultado foi inventado.

## Fronteiras / dependências de outros agentes

### CHAT 2 — importação PPTX/Canva

Este trabalho consome `PptxImporter`. Nenhuma refatoração ampla do importador foi feita.

### CHAT 4 — ProductCards/bindings

Nenhuma alteração grande em ProductCards. O contrato `find_image()` está pronto para consumo futuro.

### CHAT 5 — QA

Pode consumir os novos testes, métricas do inventário e corpus real para regressão/performance.

### Integração mínima necessária no shell

Arquivo:

- `src/srstudio/app/professional.py`

Função:

- `_attach_project`

Interface necessária:

```python
self.image_library = SafeImageLibrary(self.data_dir / "images")
```

Motivo:

- levar fail-closed persistence, full SHA/provenance e dedupe perceptual conservadora ao Studio visual principal sem mudar o contrato de `ImageBankView`/workflow.

## Próximos ciclos independentes

1. criar ingestão conservadora de standalone assets com catálogo + provenance explícita;
2. executar todo o novo corpus pelo batch dentro de um checkout/CI que tenha o repositório e registrar as métricas finais de decisões `accepted/probable/review/decorative`;
3. medir ingestão/hash/indexação/lookup em banco populado;
4. validar buscas reais quando houver imagens aprovadas para os SKUs;
5. depois da integração do `SafeImageLibrary` no shell, testar fluxo UI → banco → ProductCard sem alterar o domínio do CHAT 4.

## Commits CHAT 8 desta sessão

- `721ec2667c65fc9862a132d62e00dd094b94d0d1` — Recovery Audit + baseline inicial.
- `8a204a5ae0fd8d456645f601071480a6904e7407` — consenso source-content-aware.
- `2ed879feeab2e58ef275e37cdf4b3c34a8eb4ce2` — testes de identidade documental.
- `da8da265c2e99cd491d701a2f25f45f89c0569b6` — gate perceptual conservador.
- `fe62b485f241e777024826c34c176ab0aeec7aaa` — SafeImageLibrary com dedupe segura.
- `41ffb0552f63e5daf0ca3b348dc0ebf95008ec52` — testes iniciais de colisão dHash.
- `a658a407e2c5967a8ceb7a248da0951624ae3036` — comando batch inicial.
- `97ded045b5f24b3a2a576317f274447671b3b517` — contrato/report batch.
- `bc7ac2ce0a5b8c7b6496566e62ec2726be3f3aeb` — SHA-256 completo em provenance.
- `273413635b0744f8aea073bd94587587312e99ce` — merge de provenance e SHA canônico de variantes.
- `60ad35428fe96a4e4aad483f48e546a53ac427e6` — aliases por variantes visuais conhecidas.
- `18077b5574155ecd3d4ad7eb910a7257ad28e955` — testes de provenance de near-duplicate.
- `a09f4cfc2936c4be417d93ae14c42f7ee4b9d80a` — testes de aliases por variante SHA.
- `606fcd62c17b30d31e25f9dc2ee0f5c0c619edb3` — fingerprint lógico + reprocessamento incremental por versão de precisão.
- `5e0cb0386fc7d18d3753315704e15b03083ce4f4` — testes de fingerprint/upgrade incremental.
- `fe9636a80abaa072b07d3bce02a7518fb85426b0` — template conflict → decorative.
- `40cca733abc245ce623232b989006209b8ca4011` — testes de classificação de template.
- `a181b64ac537d7be160ae30f842637ec3f538aaa` — inventário estruturado PPTX.
- `65d769c861cf10c4c38c96f9dde9b473fee16774` — testes do inventário.
- `c993a43d7b2595ff52ffa8bb88696cec23f13774` — inventário integrado ao batch.
- `9349b11fa17cf4270f9ee418fffa164e25e480c3` — teste do batch inventory-first.
