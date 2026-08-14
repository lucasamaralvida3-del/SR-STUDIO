# SR Studio

Ferramenta desktop do SR para criação e gerenciamento de cartazes, atacado, promoções e encartes.

## Linha atual de produção

- Stable pública: `4.0.16-hybrid.stable4`
- Beta pública: `4.0.16-hybrid.beta19`
- Instalador: `4.0.16-setup2`

Essas versões permanecem preservadas enquanto a próxima geração é construída.

## Próxima geração: SR Studio 5.0

O desenvolvimento da 5.0 acontece na branch `next/5.0`.

### Fonte de verdade

`src/sr_studio/`

A fonte canônica foi materializada diretamente do pacote publicado da Stable 4 e validada por SHA-256 antes da migração. Os antigos diretórios `staging/betaXX` passam a ser apenas histórico da linha 4.x.

### Estrutura

- `src/sr_studio/` — aplicação canônica
- `src/sr_studio/core/` — núcleo e regras fundamentais
- `src/sr_studio/services/` — serviços compartilhados
- `src/sr_studio/modules/` — módulos de negócio
- `src/sr_studio/ui/` — interface compartilhada
- `src/sr_studio/data/` — persistência, schemas e migrações
- `tests/` — testes automatizados
- `build/` — materialização e empacotamento
- `docs/` — arquitetura, roadmap e legado
- `launcher/` — atualizador/launcher
- `installer/` — instalador Zero Admin

## Documentação

- `docs/ARCHITECTURE_5.md` — arquitetura e critérios de liberação
- `docs/ROADMAP_5.md` — escopo funcional completo da 5.0
- `docs/LEGACY.md` — regras para o legado 4.x

## Regra de release 5.0

Stable e Beta serão empacotadas a partir da mesma árvore `src/sr_studio/`. A 5.0 não substitui a Stable atual até passar pelos testes de instalação, atualização, rollback, XLSX/PPTX, projetos, banco de produtos, Encartes, geração e exportação.
