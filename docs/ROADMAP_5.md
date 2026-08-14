# Roadmap — SR Studio 5.0

A versão 5.0 será um salto de produto e arquitetura. O desenvolvimento acontece integralmente em `next/5.0`, usando `src/sr_studio/` como única fonte de verdade. Stable 4 e Beta 19 permanecem publicadas e disponíveis para rollback até a conclusão da 5.0.

## Escopo funcional da 5.0

### 1. Gerenciador de Projetos
- Tela “Meus Projetos”.
- Criar, abrir, renomear, duplicar, arquivar e excluir.
- Projetos recentes.
- Autosave.
- Recuperação após fechamento inesperado/queda de energia.
- Formato de projeto `.srstudio` com dados, páginas, produtos, ajustes e referências de assets.
- Histórico e versões recuperáveis.

### 2. Gerenciador de Modelos Canva/PPTX
- Importação de PPTX.
- Reconhecimento automático de campos.
- Modo de configuração manual de campo por clique.
- Tipos: IMAGEM, NOME, R$, REAIS, CENTAVOS, UNIDADE, PREÇO APP, LIMITE e TEXTO FIXO.
- Salvar modelo aprendido.
- Biblioteca de modelos e campanhas.
- Reutilização sem novo reconhecimento.

### 3. Banco Central de Produtos
- Código interno/CISS.
- EAN/código de barras.
- Nome original.
- Nome comercial.
- Categoria.
- Unidade.
- Imagem oficial.
- Aliases/sinônimos.
- Histórico de correções.
- Indicadores de produto sem imagem, baixa resolução, duplicidade e cadastro incompleto.
- Banco compartilhado entre Cartazes, Atacado, Promoções e Encartes.

### 4. Importador Inteligente de Planilhas
- Mapeamento de colunas na primeira importação.
- Perfis salvos de planilhas/relatórios.
- Reconhecimento de Código, Nome, Preço, Preço APP, Entrada, Limite etc.
- Prévia antes da importação.
- Contagem de reconhecidos, novos, inválidos e sem imagem.
- Validação de preço/unidade/limite.

### 5. Assistente de Campanha
- Fluxo guiado: campanha -> planilha -> produtos -> modelo -> páginas -> gerar.
- Distribuição automática de produtos.
- Múltiplas páginas.
- Regras por categoria/destaque.
- Manutenção da liberdade de edição manual depois da montagem automática.

### 6. Central de Validação / Pré-impressão
- Produto sem imagem.
- Imagem com baixa resolução.
- Preço vazio/zerado/inválido.
- Unidade suspeita.
- Texto cortado.
- Sobreposição crítica.
- Elemento fora da página.
- Fonte ausente.
- Produto repetido.
- Limite inválido.
- Slot vazio.
- Status final “Pronto para imprimir” ou lista de pendências.

### 7. Central de Exportação
- PDF completo.
- PNG por página.
- A4.
- A3.
- Instagram Feed 1080x1350.
- Instagram Story 1080x1920.
- WhatsApp.
- Perfis reutilizáveis.
- Preparação para redimensionamento inteligente entre formatos.

### 8. Atualização, Histórico e Rollback
- Tela de versão instalada.
- Verificar atualizações.
- Exibir canal Stable/Beta.
- Histórico de releases.
- Rollback seguro para última versão funcional.
- Manter Launcher e instalador independentes da aplicação.

### 9. Arquitetura e Manutenção
- Fonte canônica em `src/sr_studio/`.
- Camadas `core`, `services`, `modules`, `ui`, `data`.
- Remoção gradual de dependência dos patches `staging/betaXX`.
- Empacotador único.
- Stable e Beta geradas da mesma árvore.
- Migrações de dados versionadas.

### 10. Testes e Documentação
- CI obrigatório.
- Compilação Python.
- Validação JavaScript.
- Testes de projeto e banco de produtos.
- Testes XLSX/PPTX.
- Testes de exportação.
- Teste do instalador no Windows.
- Teste de atualização e rollback.
- Documentação de arquitetura e formatos.

## Ordem interna de construção

Embora a versão seja liberada como um único grande salto, a implementação interna será feita nesta ordem para reduzir dependências:

1. Persistência e schemas (`data` + `core`).
2. Projetos/autosave.
3. Banco central de produtos.
4. Perfis de importação de planilha.
5. Registro e aprendizado de modelos PPTX.
6. Assistente de campanha.
7. Central de validação.
8. Exportação multiperfil.
9. Tela de atualização/rollback.
10. Integração final com todos os módulos existentes.
11. Testes Windows ponta a ponta.
12. Publicação Beta 5.0 e, após validação, Stable 5.0.

## Regra de publicação

Nenhuma parte intermediária da 5.0 substitui a Stable atual. A linha `next/5.0` só será publicada em canal de teste quando o fluxo completo estiver utilizável. A Stable 5.0 somente será promovida quando todos os testes de migração, geração, exportação, atualização e rollback passarem.
