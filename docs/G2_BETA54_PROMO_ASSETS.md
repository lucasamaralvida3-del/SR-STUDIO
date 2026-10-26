# SR Studio G2 — acervo de campanhas (Beta 54)

## Origem e objetivo

O acervo foi organizado do anexo **Nova pasta (3)(1).rar** em 26/10/2026.
**Não interpretar JPG de encarte pronto como fundo editável**: os preços e produtos
já estão achatados. Os Smart Slots existentes continuam responsáveis por dados
de produto, unidade, preço normal, promocional e NO CLUBE SR.

## Mapeamento recomendado

| Campanha | Fundo limpo | Selo/logo WebP | Referência não editável |
| --- | --- | --- | --- |
| Terça Verde | `fundos/terca-verde.jpg` | `selos/terca-verde.png` extraído do PPTX original | `referencias/terca-verde-produto-e-preco.jpg`, `referencias/layout-terca-verde.pptx` |
| Quarta Café com Pão | `fundos/quarta-cafe.jpg` | `selos/quarta-cafe.png` | `referencias/quarta-cafe-produto-e-preco.jpg` |
| Quinta Filé | `fundos/quinta-file.jpg` | `selos/quinta-file.png` e variações regionais | `referencias/quinta-file-produto-e-preco.jpg` |
| Churrasco/Açougue | `fundos/churrasco-acougue.jpg` | `selos/churrasco.png`, `selos/acougue.png`, `selos/acougue-premiado.png` | o próprio fundo, sem preço, é referência de cenário |

O arquivo `produtos/10310321-m-quiabo.jpg` é imagem de produto,
**não** fundo nem selo.

## Detalhes de fidelidade observados

- Os fundos de campanha já contêm o logotipo SR e rodapé fixo.
- A data da campanha está **em branco em uma tarja colorida** nos fundos
  selecionados; não utilizar os exemplos com data/preço gravados.
- Terça, Quarta e Quinta trazem o texto fixo "VÁLIDAS SOMENTE DIA";
  o churrasco usa "VÁLIDAS DE" e poderá exigir suporte a intervalo
  de datas em etapa posterior.
- O selo é WebP com transparência, colocado independentemente
  da base do fundo; não recriar Smart Slot novo para cada campanha.
- Manter referência de 1080 × 1350, elementos legíveis e sem sobreposições.

## Estado técnico

- A Beta 53 publicada e a Stable não são modificadas por esta branch.
- Os novos comandos foram ligados ao roteador do Graphics Engine 2.
- Os 4 fundos e 8 selos otimizados (WebP) estão em
  `src/srstudio/assets/campaigns/{backgrounds,seals}/`.
- O programa apresenta 12 miniaturas próprias em
  `src/srstudio/assets/campaigns/thumbs/`.
- O catálogo `catalog.json` registra SHA-256 e tamanho de cada arquivo;
  o PyInstaller inclui tudo no host G2 com `--collect-data srstudio`.
- As artes chegam no download automático da Beta pelo launcher. Nenhum ZIP
  precisa ser importado pelo usuário.
- Ao clicar no fundo, o editor coloca a arte cobrindo 100% da página, insere
  o selo padrão alinhado e aplica a paleta correspondente aos Smart Slots.
- Os fundos e selos opcionais do usuário permanecem suportados por arquivo
  local, sem ser necessário para as 4 campanhas principais.
- O release Windows deve conter todos os 24 arquivos; a promoção valida
  seus hashes SHA-256 antes de publicar o manifesto Beta.
- Exigir testes e comparação visual entre preview/exportação antes de release.

## Próxima verificação visual

Abrir o acervo interno em cada campanha, selecionar fundo e selo, testar cada layout
predefinido (1/6/7/9/11 e Multi 5/6), conferir variantes de cores,
preço e "NO CLUBE SR", testar data manual/planilha e
verificar exportação PNG/PDF antes de promover ao canal Beta.
