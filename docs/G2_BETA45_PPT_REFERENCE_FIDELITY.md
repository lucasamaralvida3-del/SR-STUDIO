# Contrato de fidelidade visual — SR Studio G2 Beta45

## Referências autorizadas

- `individual(1).pptx` (1 slide, 10287000 × 12852400 EMU): modelo individual.
- `multi slots(1).pptx` (1 slide, mesmas medidas): faixa horizontal de cinco produtos.
- A captura do editor na Beta44 documenta o problema a corrigir: caixas cinzas, textos ilegíveis/sobrepostos, preços fora da barra e fundos incompletos.

**Regra:** os arquivos originais são referência geométrica/cromática. Não converter cada slot em uma imagem plana; manter nós de produto/preço/título inteiramente editáveis e vinculados ao cadastro.

## Paleta e tipografia medida no PPTX

| Elemento | PPTX fonte | Cor | Característica |
| --- | --- | --- | --- |
| Cabeçalho dos produtos | ambos | `#105594` | fonte **Anton**, maiúsculas, alinhamento central |
| Fundo de preço | ambos | `#105594` | azul chapado, cantos arredondados |
| Preço (R$, inteiro, centavos, unidade) | ambos | `#FFFFFF` | elementos **separados**, editáveis |
| Área de produto | ambos | branco/transparente | **sem** fundo cinza ou caixa de upload visível |
| Fundo do conjunto | `multi slots(1).pptx` | branco | faixa azul contínua |

A fonte registrada no PPTX é **Anton**. O G2 preserva o nome e usa o substituto do sistema se Anton não estiver instalado; a fidelidade tipográfica precisa ser inspecionada no Windows, especialmente em tamanhos pequenos.

### Individual

A arte apresenta uma imagem de produto dominante à esquerda, título azul à direita e preço branco em uma placa azul arredondada à direita/embaixo. O slide original usa textos separados com tamanhos relativos registrados:

- Título: 28,6 pt; R$: 47,6 pt; inteiro: 99,7 pt; centavos: 38,1 pt; unidade: 27,9 pt; PROMOÇÃO: 23,3 pt.
- A imagem não fica dentro de um controle de upload cinza; a base é branca, e o **preço** é que fornece o fundo contrastante.
- O rótulo `PROMOÇÃO` aparece na linha superior do preço único. Na variação de dois preços essa linha é ocupada por valor secundário e `NO CLUBE SR`, sem textos sobrepostos.

Preset `individual-beta44` corrigido na Beta45 (mantém o ID para compatibilidade):
- imagem `[.03,.06,.54,.86]`
- título `[.57,.16,.41,.28]`
- preço/placa azul `[.53,.53,.45,.43]`
- cor de título/placa `#105594`
- sem caixa de imagem cinza ou bordas decorativas do editor;
- proibição de apagar produto, preço, IDs e vínculos salvos quando o layout for migrado.

### Multi Itens

O PPTX enviado mostra exatamente **cinco colunas horizontais** com nomes na parte superior, produtos centralizados acima do preço e uma **faixa azul única** na base. Há divisórias verticais azuis em aproximadamente 19,9%, 39,6%, 59,2% e 78,8% da largura do conjunto.

No PPTX original:
- nomes em Anton 13,6 pt, azul `#105594`;
- R$ 14,8 pt, inteiro 35,6 pt, decimal 12,6 pt, UN 12,2 pt, promo 7,1 pt;
- mesmo alinhamento visual em todas as colunas.

Contrato de criação:
- Preset `multi-cell-beta44`: texto azul no topo, imagem sem moldura entre topo e barra, preço branco na base, promo condicional.
- Grupo pai `Smart Slot Multi Itens` **é responsável** pelo papel branco, a placa azul arredondada e os separadores. Cada célula usa fundo transparente para não cobrir a placa.
- 5 itens: cinco colunas iguais; 6 itens: seis colunas iguais, extensão derivada, sem alterar a geometria interna dos elementos.
- Placa azul ocupa o trecho inferior `y=.77..1`, sem interrupção ou barras duplicadas; divisores azuis `y=.17..73`.
- O `z_index` do papel (−110) precede o fundo azul (−100); divisores e produtos ficam acima; preços/rótulos ficam acima do fundo.
- Modo de dois preços: segunda linha sem sobreposição com rótulos, números principais e unidade.

## Requisitos funcionais

- **Vincular produto:** imagem, nome, inteiro, centavos e unidade exclusivos para cada célula; não compartilhar produtos entre colunas.
- **Transformações:** mover e redimensionar grupo, slot individual e células sem trocar IDs nem perder nós decorativos.
- **Salvamento/abertura:** `GraphicsDocument.to_dict/from_dict`; migração automática de documentos Beta44 sem apagar o conteúdo vinculado; a migração deve ser idempotente.
- **Layouts 6/7/11:** reutilizar esses dois presets, não desenhos achatados nem caixas genéricas; layout de 11 mantém a faixa Multi5.
- **Qt Quick / Qt renderer:** verificar imagens reais do canvas, não apenas existência do arquivo PNG exportado. Teste de pixels deve detectar azul de referência em áreas específicas.
- **Não modificar** a versão Beta44 publicada, a Stable ou o manifesto do launcher sem aprovação dos testes reais Windows e revisão visual.

## Entrega e verificação

Branch: `feature/g2-beta45-reference-fidelity`, PR #134.
Workflow: `G2 Beta45 PPT Reference Fidelity`.
Artefato: PNGs reais de Individual, Multi5 e Multi6 para revisão visual no Actions. O ZIP da Beta44 permanece válido até a próxima Beta aprovada.
