# SR Studio 5.0 Professional — Blueprint

Status: implementação em branch isolada `sr-studio-5-professional`.

## Regra principal
A versão 4.x permanece preservada e utilizável. O 5.0 será construído em paralelo e migrará recursos de forma controlada.

## Identidade visual aprovada
A interface do SR Studio e do Encartes Studio deve seguir a referência visual aprovada:
- sidebar azul escuro fixa com logo SR em bloco arredondado;
- superfície principal clara;
- cards brancos, cantos arredondados e bordas/sombras discretas;
- azul como cor primária de ação;
- navegação consistente entre Studio e Encartes;
- barra superior com busca/command palette, estado do projeto e ações principais;
- tipografia limpa, hierarquia forte e alta densidade sem poluição;
- Encartes Studio em três áreas: biblioteca/ferramentas à esquerda, canvas no centro, propriedades à direita;
- miniaturas de páginas abaixo do canvas;
- produto na biblioteca sempre pode exibir miniatura, nome, preço, unidade, status e ação de adicionar.

## Shell principal
- Início
- Central 5.0
- Encartes Studio
- Banco de Produtos
- Planilhas
- Modelos
- Validação
- Exportação
- SR IA
- Configurações

## Arquitetura alvo
```text
src/srstudio/
  app/
  core/
  editor/
  products/
  projects/
  importers/excel/
  importers/pptx/
  templates/
  pricing/
  images/
  intelligence/
  validation/
  export/
  diagnostics/
  updater/
  settings/
tests/
assets/
templates/
installer/
build/
docs/
```

## Modelo central de produto
Campos-base: id, código, EAN, nome original, nome de exibição, preço, preço APP, atacado, varejo, unidade, quantidade, limite CPF, categoria, imagem, campanha, validade, origem e confiança do reconhecimento.

## Encartes Studio
### Card inteligente
Imagem + nome + preço + unidade + limite pertencem a um `ProductCard`, mas continuam editáveis individualmente.

### Biblioteca de produtos
- miniatura real ao lado do produto;
- busca e filtros;
- preço/unidade visíveis;
- status de imagem/dados;
- adicionar por clique;
- drag & drop para canvas;
- substituir card mantendo design;
- ações em lote.

### Editor
- seleção simples/múltipla;
- resize, rotação, lock, group/ungroup;
- layers;
- copy/paste e clipboard entre projetos;
- undo/redo por comandos;
- smart guides, snapping, grid, réguas e safe areas;
- zoom;
- múltiplas páginas e duplicação;
- página mestre;
- estilos vinculados;
- smart reflow e overflow para nova página;
- balanceamento entre páginas;
- collision detection;
- inspector visual;
- proof mode.

### Price Engine
Componente único para moeda, reais, centavos, unidade, APP, atacado/varejo, de/por, limite e presets. Reais/centavos permanecem magneticamente alinhados.

### Auto Layout
Grades, mosaicos, hero + normais, hortifruti, açougue, atacado e layouts por campanha. Estratégia pode ser sugerida pela IA, mas geometria final é determinística.

## Importadores
### Excel
Mapeamento tolerante de cabeçalhos, preview, reconhecimento de unidade, limite, preço, categorias, duplicados e validação antes da entrada no projeto.

### Canva/PPTX
Pipeline: slides -> elementos -> grupos -> geometria -> texto/fontes -> imagens -> relações espaciais -> semantic mapper -> cards. Permitir converter um PPTX importado em Template SR reutilizável.

## Banco local
Banco de produtos com EAN/código, nomes normalizados, imagens, categorias, histórico, preferências e cache. A integração CISS fica fora do escopo desta etapa.

## Projetos
Formato próprio versionado (`.srproject` ou equivalente), autosave, backups, snapshots, recuperação de falha, migração de schema e compatibilidade retroativa.

## SR IA / SR Intelligence
A IA nunca altera dados comerciais críticos silenciosamente. Toda ação passa pelo Core e entra no histórico de undo/redo.

Especialistas internos:
- Product Intelligence
- Layout Intelligence
- Image Intelligence
- Import Intelligence
- Copywriter
- Campaign Planner
- Quality Inspector
- Studio Assistant

Níveis: sugerir, assistir e automatizar com revisão final.

Comandos naturais devem virar ações estruturadas, por exemplo: destacar produto, reorganizar página, agrupar categorias, melhorar legibilidade e criar variação de formato.

## Validação profissional
Painel único de problemas: preços ausentes/suspeitos, imagem ausente/baixa resolução, unidade, limite, ortografia, overflow de texto, colisões, margens, fonte ausente, duplicidade e inconsistência visual.

## Exportação
Perfis para PDF de impressão/gráfica, PDF leve, PNG/JPG, Instagram 1080x1350, WhatsApp e outros formatos. Adaptação de formato deve reorganizar layout, não simplesmente esticar a página.

## Confiabilidade
- operações pesadas fora da thread da UI;
- progresso e cancelamento quando possível;
- logs rotativos e códigos de erro;
- Recovery Center;
- modo seguro;
- Health Center;
- feature flags;
- configuração central;
- uma única fonte de versão;
- Beta e Stable usando o mesmo código, diferenciados por configuração de distribuição;
- rollback do atualizador;
- testes obrigatórios antes da publicação.

## Critérios de qualidade
1. Nenhuma função nova deve duplicar regra de negócio existente.
2. Preço e dados comerciais nunca dependem de inferência generativa para cálculo.
3. Toda transformação importante é reversível.
4. Trabalho do usuário deve sobreviver a fechamento inesperado.
5. Projeto inválido deve abrir em modo recuperável quando possível.
6. Importação e exportação não podem congelar a interface.
7. O Encartes Studio deve ser especializado em varejo, não apenas imitar um editor gráfico genérico.
