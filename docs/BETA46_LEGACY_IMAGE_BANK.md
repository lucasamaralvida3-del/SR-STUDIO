# Beta 46 · recuperação segura do Banco SR de imagens

Este trabalho **não modifica o layout do editor**, não aprova automaticamente
correspondências produto/foto e não publica a Beta 46 no launcher.

## Fontes verificadas

- Release permanente: `image-db-corpus-v1`
  - `standalone-images.zip` (48.848.012 bytes)
  - SHA-256: `9c2f12d23aa827fa88124dcf82468daed42a05fb44df6ab8109e0b487dc384ff`
  - Manifest histórico: `g2/parallel-image-database/docs/parallel/phase3-evidence/phase3b-final-rerun/standalone-manifest.json`
- Validação do arquivo: 160 imagens íntegras, 153 candidatas,
  7 decorativas excluídas. Há 15 duplicatas exatas entre as candidatas.
- Recuperação comprovada no workflow GitHub:
  **138 arquivos distintos para revisão**, **zero associações aprovadas
  automaticamente**. A saída é um artefato do GitHub Actions, não um
  banco oficial sincronizado.
- O corpus mais amplo também inclui fontes PPTX antigas:
  36 apresentações, 1.910 mídias únicas nos pacotes; no relatório
  histórico de processamento havia 1.037 imagens canônicas, mas apenas
  duas associações de catálogo estavam automaticamente aprovadas.
  Essas cifras **não** representam imagens utilizáveis automaticamente
  no computador atual.
- `image-bank/manifest.json` na branch `sr-studio-5-professional`
  contém `"assets": []`. Não trocar esse manifesto por itens pendentes.

## Integração existente com o editor

O banco antigo guarda `~/.srstudio5/images/index.json` e arquivos em
`~/.srstudio5/images/assets/`. O G2 guarda fotos escolhidas manualmente
em outra biblioteca. A ponte Beta46 consulta ambas e mantém a ordem:

1. Foto de produto existente e válida no projeto;
2. Foto persistente associada manualmente ao ID/código do produto no G2;
3. **Somente** foto do banco histórico cujo estado é `accepted`,
   por EAN exato, código exato ou nome de produto integral exato.

Se houver várias fotos elegíveis diferentes, exige uma única preferida
por revisão humana; correspondências por aliases inferidos, similaridade
e fotos com `pending` / `rejected` **nunca** são usadas automaticamente.

O vínculo é inserido no catálogo na abertura/importação e também ao
colocar um produto diretamente em um Smart Slot. Os construtores e
geometrias dos Smart Slots não são modificados.

## Reproduzir a recuperação (isolado; nenhuma aprovação)

O workflow `.github/workflows/g2-beta46-recover-image-corpus.yml`
baixa a versão verificada da release, valida cada checksum e publica
um artefato temporário `beta46-legacy-image-bank-review-only`.

Também é possível executar localmente:

```shell
python tools/recover_historical_product_images_beta46.py --archive standalone-images.zip --manifest standalone-manifest.json --destination ./bank-for-review --sha256 9c2f12d23aa827fa88124dcf82468daed42a05fb44df6ab8109e0b487dc384ff
```

Para incorporar os candidatos após baixar e extrair o artefato:

```shell
python tools/install_historical_review_bank_beta46.py --source ./bank-for-review --destination ~/.srstudio5/images
```

O instalador verifica todas as fotos, ignora caminhos absolutos da máquina
do GitHub Actions, preserva registros preexistentes e deixa os novos
candidatos em **revisão pendente**. No Windows, o destino pode ser
omitido e o script usa automaticamente o diretório da conta do usuário.

Depois, as imagens devem ser identificadas por SKU/EAN e aprovadas na
biblioteca existente do SR Studio. **Não adicionar o artefato de revisão
diretamente ao manifesto do banco oficial.**

## O que permanece pendente

- Revisar e vincular as 138 fotos candidatas por identidade comprovada.
- Continuar a recuperação do corpus PPTX de aproximadamente 1.037
  imagens canônicas, também sem associações automáticas.
- Validar o fluxo real no Windows após instalar/revisar dados.
