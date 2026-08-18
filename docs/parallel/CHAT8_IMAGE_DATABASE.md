# CHAT 8 — Banco Automático de Imagens

## Recovery Audit

- Branch isolada: `g2/parallel-image-database`.
- Worktree solicitado: `../SR-STUDIO-g2-image-database`.
- BASE_SHA: `3b44feaf6480e286d3619d0a1c0c00a13a4f450c`.
- Nenhuma alteração foi feita em `main` ou `stable`.
- Nenhum merge, `reset --hard`, `clean` destrutivo ou descarte de trabalho existente foi executado.
- `docs/G2_CONTINUOUS_PROGRESS.md` permaneceu somente leitura.
- O runtime desta sessão não expõe checkout Git local do SR-STUDIO. Escritas foram feitas exclusivamente na branch isolada via GitHub connector.
- Consequência: `git status`, `git worktree list` e `pytest` completo não puderam ser executados diretamente no worktree real.

## Baseline anterior — não repetir

A auditoria anterior dos 15 PPTX continua válida e não foi refeita como fonte principal na FASE 2:

- 15 PPTX reais;
- 13 arquivos únicos exatos;
- 11 documentos lógicos;
- 295 slides;
- 363 referências de imagem;
- 545 ocorrências de texto candidato a produto;
- 124 produtos normalizados;
- 14 mídias embedded únicas;
- as 14 mídias eram essencialmente logos, fundos, selos e template;
- baseline segura: **0 fotos reais de SKU extraíveis desses 15 arquivos específicos**.

Esses arquivos continuam úteis para nomenclatura, aliases, layout e coocorrência, mas não devem ser reprocessados repetidamente em busca de fotos que não existem no pacote.

---

# FASE 2 — REAL IMAGE CORPUS

## Objetivo

A FASE 2 mudou o foco de “como associar Produto↔Imagem” para:

> onde estão as fotos reais já pertencentes ao acervo do SR e como transformá-las em um banco confiável, incremental e reutilizável sem trabalho manual.

A prioridade permanece **precisão antes de cobertura**. `wrong-auto-accept` continua sendo o pior erro possível.

## 1. Compactados encontrados na Library

Foram encontrados 8 arquivos compactados não gerados pelo modelo:

1. `Downloads(1)(1).zip` — 249.253.663 bytes;
2. `Downloads(2)(1).zip` — 344.039.590 bytes;
3. `Downloads(2).zip` — 344.039.590 bytes;
4. `Downloads(1).zip` — 249.253.663 bytes;
5. `modelos.zip` — 2.953.526 bytes;
6. `publish_repository.zip` — 19.093.966 bytes;
7. `Downloads.zip` — 1.577.959 bytes;
8. `Downloads.rar` — 1.580.383 bytes.

### 1.1 Duplicatas exatas de arquivos grandes

SHA-256 confirmou:

- `Downloads(1)(1).zip` == `Downloads(1).zip`
  - SHA-256: `aae355ed0ddcb60867172cf11b637553bf1f292c488c536ca090d15472ca79ba`
- `Downloads(2)(1).zip` == `Downloads(2).zip`
  - SHA-256: `035789d47d06e8f2667d776c023b055e5d68b8c2240f98d5f775289874fbfd86`

Portanto apenas **2 arquivos grandes únicos** precisam representar esse corpus.

### 1.2 Downloads.zip / Downloads.rar

Os dois arquivos contêm os mesmos 6 JPGs da campanha de Dia dos Pais.

A equivalência foi confirmada pelos 6 pares de:

- nome interno;
- tamanho;
- CRC32.

Eles são artes compostas de campanha, não fotos standalone de SKU.

### 1.3 modelos.zip

`modelos.zip` contém 17 PPTX de uma página.

Medição:

- 17 slides;
- 35 ocorrências de mídia;
- somente 5 mídias únicas.

Inspeção visual: logos SR, QR, faixas e elementos de template. **0 fotos reais de SKU**.

### 1.4 publish_repository.zip

O pacote publicado contém 126 entradas, incluindo:

- 17 `.pptx`;
- 8 `.png`;
- 17 `.py`;
- 19 `.ps1`;
- 7 `.xlsx`;
- 1 SQLite `atacado_historico.db`;
- executáveis/bibliotecas/scripts de publicação.

Os 8 PNGs são thumbnails de modelos + logo SR.

Os 17 PPTX possuem somente **10 hashes de PPTX únicos**, e o conjunto desses 10 hashes é exatamente igual ao conjunto lógico de `modelos.zip`.

Resultado: `publish_repository.zip` **não adiciona nova fonte de foto de SKU**, mas trouxe um catálogo real de atacado muito valioso.

---

## 2. Descoberta decisiva — dois ZIPs ricos em fotos reais

Os dois arquivos grandes únicos contêm os encartes que faltavam na FASE 1.

### Downloads(1)(1).zip

Contém 13 PPTX reais de campanhas, incluindo:

- churrasco/açougue;
- Ambev/Copa;
- Relâmpago;
- limpeza;
- economia;
- Terça Verde;
- Quarta Café com Pão;
- Quinta Filé;
- Baby;
- cervejas/bebidas;
- especiais;
- fim de semana;
- hortifruti.

Métricas aproximadas do pacote:

- 13 PPTX;
- 257 slides;
- 1.059 entradas de mídia;
- 892 mídias únicas exatas dentro do arquivo.

### Downloads(2)(1).zip

Contém 23 PPTX reais, incluindo materiais SANJU, bebidas, fim de semana, shampoo Siàge, mussarela, KitKat, pescados, sorvete, carnes, Heineken, Batata Bem Brasil, terça/hortifruti/limpeza etc.

Métricas:

- 23 PPTX;
- 309 slides;
- ~1.265 entradas de mídia.

### Corpus rico combinado

Os dois arquivos grandes únicos representam:

- **36 PPTX**;
- **566 slides**;
- **2.324 ocorrências/entradas de mídia**;
- **1.910 mídias únicas exatas por SHA-256**;
- **234 grupos de hash duplicado**;
- **414 ocorrências duplicadas além dos canônicos**.

A inspeção visual confirmou que esse corpus contém muitas fotos/cutouts reais de produto: arroz, feijão, flocão, tapioca, café, açúcar, leite, achocolatado, limpeza, fraldas, hortifruti, carnes, cervejas, vinhos e outros SKUs.

Este é o primeiro corpus encontrado nesta missão que realmente pode popular o banco em escala.

---

## 3. Frequência de produto no corpus rico

O novo `product_priority.py` conta produtos pelo texto estruturado dos PPTX independentemente da associação de imagem.

Ele:

- lê PPTX direto;
- lê PPTX dentro de ZIP sem extração destrutiva;
- deduplica inner PPTX por SHA-256;
- deduplica exportações semanticamente equivalentes por fingerprint slide/produto;
- não usa imagem encontrada como requisito para um produto entrar no ranking.

Baseline real atual dos dois ZIPs ricos, com o classificador atual:

- 36 documentos estruturados;
- **1.612 ocorrências de produto**;
- **914 produtos normalizados úteis** na medição consolidada usada para coverage.

Produtos recorrentes observados incluem:

- CERVEJA SKOL 18X350ML — 19;
- CERVEJA AMSTEL 12X350ML — 18;
- CERVEJA ANTARCTICA BOA PILSEN 18X350ML — 17;
- CERVEJA BRAHMA 18X350ML — 16;
- CERVEJA KAISER 12X350ML — 15;
- CARNE MOIDA — 14;
- BANANA NANICA — 14;
- CERVEJA HEINEKEN SHOT 250ML — 13;
- ARROZ PATOSUL 5KG — 13;
- TOMATE PERA — 12;
- MAMAO FORMOSA — 11;
- ARROZ VASCONCELOS 5KG — 10;
- BANANA PRATA — 10;
- DETERGENTE YPE 500ML — 9;
- ACUCAR DELTA 5KG — 8;
- AMACIANTE YPE 2L — 8.

Prioridade conceitual:

`frequency + independent_sources + catalog_presence`

---

## 4. Associação calibrada no corpus real

A primeira calibração mostrou que centro geométrico puro podia trocar imagens entre linhas de grids repetidos.

`spatial_pair_score()` passou a usar:

- overlap horizontal;
- alinhamento horizontal de centros;
- distância entre bordas verticais mais próximas;
- proximidade geral;
- área relativa da imagem;
- product likelihood;
- group signal;
- z-order.

Isso atende melhor aos templates reais em que o nome fica imediatamente acima ou abaixo da embalagem.

### Gate de auto-accept

Uma única fonte PPTX, mesmo com geometria local excelente, **não pode auto-aprovar** a imagem.

Auto-accept exige também:

- confiança suficiente;
- consenso suficiente;
- **pelo menos 2 documentos lógicos independentes**.

Isso protege contra logo/selo/template que por acaso ocupe a mesma célula visual.

### Baseline de decisões no corpus rico

Protótipo calibrado sobre os dois ZIPs ricos:

- 1.065 pares de evidência Produto↔Imagem;
- 826 imagens com decisão;
- 37 decisões de imagem `AUTO_APPROVED`;
- 691 `LIKELY`;
- 86 `REVIEW_REQUIRED`;
- 12 `DECORATIVE`.

No nível de produto contra os 914 nomes estruturados:

- **35 AUTO_APPROVED — 3,83%**;
- **527 LIKELY — 57,66%**;
- **51 REVIEW_REQUIRED — 5,58%**;
- **301 sem associação exata — 32,93%**.

Ponderado pelas 1.612 ocorrências:

- AUTO_APPROVED: 195 — 12,10%;
- LIKELY: 946 — 58,68%;
- REVIEW_REQUIRED: 105 — 6,51%;
- sem candidato: 366 — 22,70%.

Ou seja: aproximadamente **77,3% das ocorrências de produto do corpus rico já possuem algum candidato** na baseline calibrada.

Esses números são baseline de engenharia do protótipo/calibração local; a execução oficial do pipeline completo no worktree ainda precisa ser feita quando houver checkout/CI disponível.

---

## 5. Precisão visual amostral

Foi gerada uma contact sheet local com 30 auto-approvals do corpus rico.

Amostra visual manual:

- avaliados: **30**;
- corretos: **30**;
- `wrong-auto-accept`: **0/30**;
- precisão amostral observada: **100%**.

Exemplos verificados incluem:

- ARROZ PATOSUL 5KG;
- DETERGENTE YPE 500ML;
- AMACIANTE SMART 2L;
- LEITE TRIANGULO 1L;
- PROTEX 85G;
- BANANA NANICA;
- TOMATE PERA;
- carnes;
- bebidas.

Esse **100% é somente da amostra de 30**, não uma alegação de precisão absoluta do banco inteiro.

A métrica crítica continua sendo `wrong-auto-accept`.

---

## 6. Catálogo real disponível

`publish_repository.zip` contém:

`publish_repository/beta/files/dados/atacado_historico.db`

Tabelas relevantes:

- `produtos` — 520 produtos;
- `itens_relatorio` — 3.116 linhas históricas;
- `cartazes_relatorio` — 1.553 linhas;
- `regras_agrupamento` — 57 regras;
- `membros_grupo` — 320 membros.

A tabela `produtos` usa:

- `codigo`;
- `ultimo_nome`;
- `unidade_preferida`;
- flags de agrupamento/ignore;
- atualização.

`standalone_cli.catalog_names_from_sqlite()` foi fortalecido para descobrir schemas como:

- `display_name`;
- `name`;
- `product_name`;
- **`ultimo_nome`**;
- `descricao`;
- `description`.

O SQLite é aberto em `mode=ro`; nenhum schema é alterado.

### Coverage atual contra os 520 produtos desse catálogo de atacado

Antes de consumir toda a Library standalone, a associação estruturada do corpus rico cobre:

- AUTO_APPROVED: **8 / 520 — 1,54%**;
- LIKELY por nome exato: **35 / 520 — 6,73%**;
- REVIEW_REQUIRED: **3 / 520 — 0,58%**;
- sem associação exata: **474 / 520 — 91,15%**.

Uma equivalência extremamente conservadora por **mesmos tokens + mesma medida**, apenas reordenados, recupera mais 5 nomes como `LIKELY`:

- LIKELY: **40 / 520 — 7,69%**;
- sem candidato: **469 / 520 — 90,19%**.

Exemplos de reordenação segura observados:

- `CERVEJA HEINEKEN 250ML SHOT` ↔ `CERVEJA HEINEKEN SHOT 250ML`;
- `AMACIANTE YPE 5L ACONCHEGO` ↔ `AMACIANTE YPE ACONCHEGO 5L`.

O percentual baixo do catálogo de atacado não contradiz a cobertura de 77,3% das ocorrências dos encartes: o catálogo possui muitos produtos que simplesmente não aparecem nos 36 PPTX ricos atuais.

---

## 7. Library standalone real

`files.list` encontrou **160 imagens não geradas pelo modelo** na Library acessível.

A busca semântica do índice da Library falhou por autenticação do serviço de retrieval; isso não foi interpretado como corpus vazio. O inventário por metadata/list foi usado como fonte de verdade.

### Imagens standalone já verificadas

#### Flocão Sinhá 400g

Arquivo:

`Farinha-de-Milho-Flocao-Sinha-Pacote-400g.webp`

- 1000×1000;
- packshot limpo;
- embalagem Sinhá Flocão 400g;
- catálogo de atacado possui `FLOCAO DE MILHO SINHA 400G`.

Candidato forte de identidade.

#### Amaciante Smart 2L

`discount_image_c576cca9e80f70b8.png`

- packshot limpo;
- Smart Carinho 2L;
- útil no banco mesmo sem aparecer no catálogo de atacado atual.

#### Feijão Paraná 1kg

`discount_image_285d2c91df21481e (1).png`

- packshot recortado;
- Feijão Paraná 1kg;
- catálogo contém `FEIJAO PARANA T1 1KG`.

#### Mandioca 1kg

`discount_image_bb4201d68b4dae2f.png`

- 400×400 RGBA;
- produto recortado;
- possui cópia exata na Library.

#### Carvão Gobbo 3kg

`imagem carvao.jpg`

- 1536×2048;
- produto e 3kg claramente visíveis;
- identidade forte;
- qualidade visual inferior a um packshot por conter corredor/caixas/produtos ao fundo.

Isso valida a separação:

1. identidade correta;
2. confiança;
3. qualidade visual.

#### Pão de Queijo Rodrigues 1kg

`pão de queijo sr.png`

A embalagem mostra SR Rodrigues, Pão de Queijo Tradicional, 1kg. O corpus possui grafias como `PAO DE QUEIJO CONGELADO SR TRADICIONAL 1KG`.

Deve entrar por alias/evidência, sem fingir que os textos são idênticos.

#### Hambúrguer Caseiro Gourmet SR 145g

`discount_image_13069c053d510d0a.png`

A embalagem mostra SR Rodrigues, Hambúrguer Caseiro Gourmet, 145g. O corpus possui variantes textuais de 145g. Gramaturas de 95g/360g não podem ser fundidas.

#### Farinha Beiju 350g

`farinha.png`

A embalagem é `Farinha Artesanal Beiju Temperada com Pimenta 350g`.

Não deve ser confundida com `FARINHA CASEIRINHA ... 350G` apenas porque ambas têm 350g.

#### Ração Caramelo 15kg

`RAÇÃO CARAMELO.jpg`

Identidade de Caramelo Dog 15kg é visível, mas é fotografia com fundo/prateleira. Pode ser candidata de identidade com quality score inferior a packshot limpo.

### Duplicatas standalone reais confirmadas

SHA-256 byte a byte:

`imagem carvao.jpg` == `imagem carvao(1).jpg`

- SHA-256: `1b857a0e36a9e14f4df1d91a5a5ee2645c2a91ee3ea0f0f68fe036b0220fd1e0`

`discount_image_bb4201d68b4dae2f.png` == cópia `(1)`

- SHA-256: `2f9848e3ba1a973d553ac16432b72894c53d5088756bf2a679dc718d575db821`

Isso valida a deduplicação exact duplicate com corpus real standalone.

---

## 8. Ingestão standalone incremental

Foi corrigida uma inconsistência real da branch: `standalone_state.py` e o teste de recovery existiam, mas a versão corrente de `standalone_cli.py` não expunha `run_incremental_standalone()`.

O fluxo incremental foi restaurado.

Fingerprint contém:

- caminho resolvido;
- SHA-256 do arquivo;
- label/mapping;
- flag `verified`;
- provenance;
- versão de treino;
- hash do catálogo.

Regras:

- input idêntico → skip;
- imagem alterada → reprocessa somente ela;
- mapping alterado → reprocessa;
- catálogo alterado → reprocessa;
- state aponta para `image_id` removido → reprocessa e recupera;
- state corrompido → fail-closed;
- backup lógico permanece.

Filename sozinho nunca auto-aprova.

---

## 9. Archive provenance

`PrecisionProductImageCorpusTrainer` passou para:

`PRECISION_TRAINER_VERSION = g2-image-precision-v3`

Para PPTX dentro de ZIP, provenance registra:

- `source_kind = archive-pptx`;
- caminho do arquivo compactado;
- SHA-256 do arquivo compactado;
- caminho interno do PPTX;
- tamanho do membro;
- CRC32;
- SHA-256 do PPTX interno.

Importante:

**archive provenance não cria voto extra de consenso.**

O fingerprint lógico do PPTX ignora o caminho do ZIP, portanto copiar o mesmo inner PPTX para outro compactado não fabrica uma nova fonte independente.

A extração usa diretório controlado e nome determinístico com hash do caminho interno, evitando colisões quando dois membros têm o mesmo basename.

---

## 10. Deduplicação e índice perceptual

Foi encontrada uma inconsistência interna: testes já esperavam `_perceptual_snapshot()` / `_perceptual_candidates()`, mas a versão corrente de `SafeImageLibrary` ainda percorria linearmente todos os assets.

Correção:

`SafeImageLibrary` agora usa efetivamente `HammingPerceptualIndex`/BK-tree.

Fluxo:

```text
nova imagem
→ dHash
→ BK-tree gera candidatos próximos
→ filtro de product_key quando aplicável
→ orientação/aspect ratio
→ assinatura RGB compacta
→ somente então near-duplicate
```

SHA-256 continua sendo identidade exata.

dHash nunca é suficiente sozinho.

O cache é invalidado:

- em gravação própria;
- quando mtime/tamanho do índice mudam externamente.

---

## 11. Ranking de qualidade da imagem

O `ImageQualityAnalyzer` existente foi estendido em vez de duplicado.

A API histórica `inspect()` continua disponível.

Foi adicionado `product_quality()` com score 0–1 calculado uma vez na ingestão a partir de:

- resolução;
- transparência útil;
- sharpness/edge signal;
- limpeza de borda/background;
- penalidades conhecidas de texto/preço;
- múltiplos produtos;
- produto parcial;
- watermark;
- fundo poluído.

`SafeImageLibrary` persiste esse score em metadata.

O lookup não abre pixels para ranquear interativamente.

### Regra de ranking

**Identidade sempre vem antes de estética.**

Ordenação conceitual:

1. identity/name/SKU compatibility;
2. manual preferred;
3. confidence;
4. visual quality;
5. usage count.

Uma foto perfeita de `TODDY 750G` jamais pode vencer uma foto inferior, porém correta, de `TODDY 370G`.

---

## 12. Contrato `find_image()`

A API continua compatível:

```python
result = find_image(library, product_name, alternatives=3)
```

Agora expõe também:

- `best_match`;
- `alternatives`;
- `confidence`;
- `match_type`;
- `quality_score`;
- `provenance`.

Cada candidato inclui:

- `identity_score`;
- `quality_score`;
- `match_type`;
- provenance;
- score/reason.

`batch_training.py` foi alinhado a esse contrato.

---

## 13. Raster/PPTX correlation

Quatro arquivos opacos da Library:

- `1000255371.jpg`;
- `1000255372.jpg`;
- `1000255373.jpg`;
- `1000255374.jpg`;

foram identificados como exports raster do deck:

`OFERTAS QUINTA FILÉ NOVO (1).pptx`

Eles correspondem aos slides **12–15**.

O PPTX possui os assets embedded, portanto o raster é referência/QA e não fonte preferencial de crop.

Foi criado `raster_correlation.py`.

Regras:

1. OCR opcional apenas encontra o slide equivalente;
2. PPTX estruturado é autoridade de nomes/regiões;
3. se o slide possui imagem embedded → `source_preference = embedded-original`;
4. **nenhum crop raster é criado** nesse caso;
5. se não houver asset embedded, pode existir crop de card;
6. crop de card é sempre `review`;
7. metadata marca `contains_text_probability = 1.0` e price probability quando aplicável;
8. crop nunca é auto-aprovado como foto limpa de produto.

Isso evita colocar nome/preço/fundo no banco como se fosse embalagem isolada.

---

## 14. Product coverage e Top Missing

`library_audit.py` foi fortalecido com:

- imagens físicas;
- assets canônicos;
- observações brutas/provenance;
- exact duplicate observations;
- near-duplicate variants;
- accepted;
- likely;
- review-required;
- rejected;
- decorative;
- imagens sem produto;
- produtos com múltiplas imagens;
- associações sem provenance;
- associações de baixa confiança;
- coverage do catálogo;
- produtos sem accepted;
- produtos sem qualquer candidato;
- queries finais;
- `priority_missing`.

`products_without_image` mantém a semântica histórica “sem imagem accepted”.

Novo campo:

`products_without_any_image`

significa que não existe accepted, likely ou review-required utilizável.

### Top Missing

`product_priority.py` alimenta `priority_missing` com produtos frequentes nos encartes mas sem candidato no banco.

O objetivo é pedir/baixar externamente apenas o que realmente faltar em uma fase posterior.

Exemplos importantes ainda faltantes/ambíguos na baseline exata incluem:

- `PAO DE QUEIJO CONGELADO SR TRADICIONAL 1KG`;
- `FARINHA CASEIRINHA TEMP C E S PIMENTA 350G`;
- `HAMBURGUER CASEIRO GOURMET SR 145G`;
- `CERVEJA PURO MALTE PILSEN 350ML`;
- `QUEIJO CAIPIRA FAZENDA SAPECADO`;
- `SURUBIM ARMAZEM DO PEIXE 800G`;
- `SIDRA CERESER CELEBRATE 660ML`.

Alguns desses já possuem standalone visualmente promissor e deverão sair do Top Missing quando a Library inteira for executada pelo pipeline oficial.

---

## 15. Review queue e contact sheet

Foi criado `review_contact_sheet.py`.

O dataset de revisão é **impact-first**:

1. prioridade/frequência do produto;
2. número de fontes;
3. pending/ambiguidade;
4. confidence;
5. quality.

Ele evita uma lista gigante.

Regras:

- rejected/decorative são excluídos;
- um único accepted sem ambiguidade não entra;
- múltiplas variantes accepted sem `preferred` podem entrar;
- número de candidatos por produto é limitado;
- thumbnails são abertas uma por vez;
- JSON de dataset pode ser gerado sem UI do Studio;
- PNG contact sheet é opcional.

---

## 16. Departamentos

Foi criado `departments.py` com classificação lexical conservadora para:

- hortifruti;
- açougue;
- bebidas;
- limpeza;
- padaria;
- frios;
- congelados;
- mercearia;
- outros.

Quando a regra não é segura, retorna `outros` em vez de forçar categoria errada.

---

## 17. Testes novos/fortalecidos nesta FASE 2

Além dos testes da FASE 1, foram adicionados ou fortalecidos:

- `tests/test_image_archive_provenance.py`;
- `tests/test_image_association.py` — grid pairing + cross-document auto-accept;
- `tests/test_image_departments.py`;
- `tests/test_image_library_audit_phase2.py`;
- `tests/test_image_lookup.py` — identity-first quality ranking;
- `tests/test_image_product_priority.py`;
- `tests/test_image_quality_ranking.py`;
- `tests/test_image_raster_correlation.py`;
- `tests/test_image_review_contact_sheet.py`;
- `tests/test_image_standalone_cli.py` — catálogo real + incremental;
- `tests/test_image_standalone_recovery.py` já existente agora volta a ter o símbolo esperado no CLI;
- `tests/test_image_safe_perceptual_index.py` agora corresponde ao BK-tree efetivamente ligado à biblioteca.

Casos cobertos incluem:

- PPTX/ZIP provenance;
- duas fontes independentes para auto-accept;
- grid row/column pairing;
- gramatura incompatível;
- qualidade não vencendo identidade;
- multiple variants;
- top missing;
- coverage;
- contact sheet;
- raster com embedded original;
- crop de fallback com texto/preço;
- incremental standalone;
- recovery de image_id removido;
- SQLite `ultimo_nome` read-only.

### Situação real de execução

Até este checkpoint:

- branch: confirmada;
- compare: **85 commits à frente do BASE_SHA** antes do commit desta documentação;
- combined CI statuses no HEAD anterior: vazio;
- workflow runs associados ao HEAD anterior: vazio;
- checkout local do repo: indisponível;
- `pytest` completo: **não executado** neste runtime.

Portanto esta documentação **não declara testes verdes sem evidência**.

---

## 18. Performance

Lookup textual continua metadata-only.

Microbenchmark anterior equivalente:

### 5.000 assets

- construção do índice: ~69 ms;
- mediana de consulta: ~0,063 ms;
- p95: ~0,071 ms.

### 50.000 assets

- construção do índice: ~730 ms;
- mediana: ~0,066 ms;
- p95: ~0,074 ms.

O maior risco de escala na ingestão perceptual foi reduzido porque o BK-tree agora está realmente conectado à `SafeImageLibrary`.

OCR continua opcional e não é executado indiscriminadamente.

Contact sheet usa thumbnails sob demanda e número limitado de candidatos.

---

## 19. P0/P1/P2/P3 — FASE 2

### P0

Nenhum P0 conhecido no caminho novo.

Proteções:

- estado fail-closed;
- backups lógicos;
- nenhuma migração destrutiva;
- archive extraction controlada;
- SHA-256 canônico;
- nenhuma associação inventada para aumentar coverage.

### P1 corrigidos/mitigados

- corpus real de fotos finalmente localizado;
- grid pairing por centro simples;
- auto-accept com uma única fonte;
- archive copies inflando consenso;
- dHash/BK-tree não conectado ao caminho seguro;
- qualidade visual misturada com identidade;
- raster page crop preferido apesar de asset embedded;
- `standalone_cli` sem o incremental esperado pelos testes;
- catálogo real `ultimo_nome` não reconhecido.

### P1 ainda aberto por execução/dado

- rodar o pipeline oficial da branch sobre os dois ZIPs ricos em um checkout real;
- rodar ingestão sobre as 160 imagens standalone acessíveis;
- persistir o banco real completo no diretório de dados do Studio;
- executar ground truth maior do que a amostra 30/30.

### P1 integração

O shell principal ainda precisa consumir `SafeImageLibrary` no ponto mínimo de integração se ainda estiver construindo `ImageLibrary` diretamente.

Essa mudança deve ser coordenada na integração final, sem invadir ProductCards/CHAT 4 durante o trabalho paralelo.

### P2

- ampliar aliases seguros por evidência;
- coverage por departamento sobre o catálogo final completo do SR, não apenas o DB de atacado disponível;
- reduzir `LIKELY` para auto-approved somente quando surgirem fontes independentes reais;
- executar benchmark de ingestão no banco completamente populado.

### P3

- UI futura de revisão;
- package-age/newer/older quando houver evidência temporal real;
- ranking visual por categoria;
- dashboards de provenance/coverage.

---

## 20. Commits principais da FASE 2

- `a9070641c71ffc0304d4e86a94c43ff1ff0a95f0` — grid spatial matching + gate de múltiplas fontes;
- `17f7cd3e7e2f00a336ffb4d8575d8bb7fe8602ec` — regressões de grid/consenso;
- `00ad517edf9b32b6c270f1cb74931b60e55dbe58` — archive provenance + precision-v3;
- `5d7cd87fc088ad0365e12e41db9deb7708db437d` — testes archive provenance;
- `bc64078c26f3b9914790b48b4291937937ffc229` — quality analyzer;
- `ecbae82be915e228b20ecdade34ae3907739d813` — BK-tree ativo + quality metadata;
- `f4171e7e488a386a6470f1154a3e2816964af366` — lookup quality/provenance;
- `b55647319112ce9018e0229ddeccb928a525d391` — testes de lookup identity-first;
- `cd1f8394304acef739789ed7ab156d72d52ef127` — testes de quality;
- `1a2153e7696c4d0418e8926114fa19ff5f146b27` — product priority;
- `353622d196ca95d4fb766a4ce0e99cbc6bc57bcc` — testes priority;
- `27b2fd43e88445a0da74618347e5214870733cef` — coverage/top missing audit;
- `f01587f79685e13ddb96d9eb4257705d393ed8e0` — testes audit fase 2;
- `b186c1643e633fc8f55f99a0db3919680270f435` — review contact sheet;
- `0fd82dbe3639437580343368c6485b15e048aa63` — testes contact sheet;
- `87d945845a58c7450671bf51b46a8b32db6f1768` — PPTX/raster correlation;
- `eaa5fcbc4c01f6af1025434635bc563e18404dfc` — testes raster correlation;
- `359fbb5a70cdc5273e23fcc9e5108db2b45fecaf` — incremental standalone + real catalog schema;
- `9b77484cd0f9a0115da985ee72a5a432e621849b` — testes standalone/catalog;
- `a06fd977bc6e53c6fb821b3b88442391aa016726` — departamentos;
- `82ee1cdb7ab2215c54d2fcd8280ac72fa2a5a354` — testes departamentos;
- `b1b24229c800c6cb88248164bb90aac948ab8044` — batch lookup contract quality/provenance.

---

## 21. Estado de sucesso da FASE 2

### Já entregue em código/engenharia

- fontes reais localizadas;
- archives inventariados;
- duplicatas de archive identificadas;
- corpus de 36 PPTX rico em fotos reais localizado;
- 1.910 mídias embedded únicas exatas descobertas;
- association grid-aware;
- consenso entre documentos;
- archive provenance;
- SHA-256 + dHash + geometria + RGB;
- BK-tree efetivamente conectado;
- qualidade visual persistida;
- lookup identity-first;
- contrato com `match_type`, `quality_score`, `provenance`;
- catálogo real de atacado descoberto e suportado;
- standalone incremental recuperado;
- raster/PPTX correlation review-first;
- product priority;
- product coverage;
- top missing;
- contact sheet;
- classificação de departamento;
- wrong-auto-accept amostral medido.

### Números reais deste checkpoint

- compactados encontrados: **8**;
- compactados grandes únicos relevantes a fotos: **2**;
- PPTX ricos: **36**;
- slides ricos: **566**;
- mídias internas: **2.324 ocorrências**;
- mídias únicas exatas: **1.910**;
- imagens standalone não geradas pelo modelo na Library: **160**;
- produtos estruturados usados na baseline de coverage: **914**;
- ocorrências de produto: **1.612**;
- decisões de imagem: **826**;
- produtos AUTO_APPROVED na baseline estruturada: **35**;
- produtos LIKELY: **527**;
- produtos REVIEW_REQUIRED: **51**;
- produtos sem associação exata: **301**;
- cobertura por ocorrência com algum candidato: **~77,3%**;
- catálogo de atacado disponível: **520 produtos**;
- `wrong-auto-accept` na amostra visual: **0/30**;
- precisão observada da amostra: **100% (30/30, não extrapolar para todo o banco)**.

### Ainda necessário para afirmar “banco real completamente populado”

1. executar a branch em checkout real;
2. rodar os dois ZIPs ricos pelo pipeline oficial persistente;
3. rodar as 160 imagens standalone pelo pipeline incremental;
4. gerar `library_audit` final do banco persistido;
5. gerar Top Missing final;
6. ampliar ground truth visual;
7. executar pytest/CI;
8. só então integrar com o Studio principal.

**A branch não deve ser mergeada em `main/stable` ainda.**

O estágio atual é de engenharia de FASE 2 avançada, com a fonte real de fotos descoberta e o pipeline preparado para transformá-la em banco confiável assim que houver execução no worktree/CI real.
