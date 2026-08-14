# Arquitetura do SR Studio 5.0

## Objetivo

A linha 5.0 elimina o desenvolvimento baseado em cadeias de patches históricos e passa a usar uma única fonte canônica, versionada e testável.

## Fonte de verdade

- Código da aplicação: `src/sr_studio/`
- Testes: `tests/`
- Build e empacotamento: `build/`
- Documentação: `docs/`
- Launcher/instalador: permanecem independentes em `launcher/` e `installer/`
- Stable 4 e Beta 19 continuam preservadas como referência e rollback durante a construção da 5.0.

## Camadas da aplicação 5.0

A migração será incremental, sem quebrar a aplicação atual.

### `src/sr_studio/core/`
Regras fundamentais compartilhadas por todos os módulos:
- versionamento interno;
- eventos;
- configuração;
- caminhos e armazenamento;
- validação base;
- modelos de domínio.

### `src/sr_studio/services/`
Serviços reutilizáveis:
- banco central de produtos;
- imagens;
- importação de planilhas;
- importação/mapeamento PPTX;
- projetos e autosave;
- exportação;
- corretor de nomes;
- histórico e backup.

### `src/sr_studio/modules/`
Módulos de negócio:
- cartazes;
- atacado;
- encartes;
- promoções;
- organizador de produtos;
- SR IA;
- integração CISS.

### `src/sr_studio/ui/`
Componentes e telas compartilhadas:
- shell principal;
- menu;
- diálogos;
- notificações;
- central de validação;
- gerenciador de projetos;
- gerenciador de modelos.

### `src/sr_studio/data/`
Schemas e migrações de dados locais:
- produtos;
- projetos;
- modelos;
- preferências;
- histórico.

## Regras de desenvolvimento

1. Toda função nova entra na fonte canônica, nunca em `staging/betaXX`.
2. Stable e Beta são geradas a partir da mesma árvore de código.
3. A diferença entre Stable e Beta é somente canal, rótulo e manifesto.
4. Nenhuma publicação acontece se os testes obrigatórios falharem.
5. O instalador sempre aponta para o manifesto do canal escolhido.
6. Mudanças de formato de dados devem possuir migração e rollback.
7. Recursos que alteram documentos nunca sobrescrevem o original sem uma cópia/versão recuperável.
8. Operações pesadas devem rodar fora da thread da interface.
9. Recursos externos/IA devem ser opcionais; o fluxo principal continua LOCAL FIRST.

## Estratégia de migração

A Stable 4 publicada é materializada integralmente em `src/sr_studio/` e serve como baseline funcional. A partir dela, componentes são extraídos do arquivo principal para as camadas acima em pequenas etapas internas, mantendo testes de equivalência. O usuário verá apenas o salto público quando a 5.0 estiver completa.

## Critério para liberar 5.0

A 5.0 só poderá substituir a Stable 4 quando:
- instalação limpa passar no Windows;
- atualização Stable 4 -> 5.0 passar;
- rollback 5.0 -> última Stable passar;
- importação XLSX e PPTX passar;
- geração de cartaz/PDF passar;
- projeto salvar/reabrir sem perda;
- banco de produtos preservar dados;
- Encartes abrir e editar;
- validação pré-impressão passar;
- pacote Stable e Beta vierem da mesma fonte canônica.
