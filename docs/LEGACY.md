# Legado da linha 4.x

Os diretórios e workflows históricos da linha 4.x permanecem no repositório para auditoria, diagnóstico e reprodução de releases antigas. Eles não são fonte de desenvolvimento da versão 5.0.

## Somente leitura / histórico

- `staging/beta*`
- `staging/stable2`
- `staging/logo_update`
- `staging/maximized_update`
- workflows de publicação específicos de Beta/Stable 4.x
- ZIP Beta 1 antigo na raiz

## Fonte ativa da 5.0

- `src/sr_studio/`: aplicação completa e canônica.
- `build/`: materialização, empacotamento e metadados.
- `tests/`: testes automatizados.
- `docs/`: arquitetura e roadmap.

## Regra

Uma correção destinada à 5.0 nunca deve ser aplicada somente em um arquivo de `staging/betaXX`. Primeiro ela entra em `src/sr_studio/` e passa pelo CI da 5.0.

## Stable/Beta 4.x

Os manifestos atuais dos canais 4.x permanecem independentes enquanto a 5.0 estiver em desenvolvimento. Isso mantém usuários atuais em uma versão conhecida e permite rollback sem depender da linha em construção.
