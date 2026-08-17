# SR Graphics Engine 2 — instalação segura do host Qt

O bundle `SRGraphicsEngine2Host` é instalado separadamente do processo Tk do SR Studio. A instalação do runtime não habilita o Engine 2: as feature flags continuam desligadas até a promoção explícita do canal experimental.

## Fluxo de instalação

`srstudio.graphics2.host_install.install_verified_host()` executa as etapas abaixo:

1. valida o catálogo SHA-256 completo do bundle fonte;
2. rejeita versão incompatível antes de tocar na instalação atual;
3. copia o bundle para uma pasta `Graphics2Host.staging-*` no mesmo volume do destino;
4. valida novamente a cópia staged;
5. grava um receipt de instalação com versão, SHA do EXE e SHA do manifesto de runtime;
6. move a instalação atual para `Graphics2Host.previous`;
7. promove o staging por rename para `Graphics2Host`;
8. valida o executável instalado e, em falha, restaura automaticamente a versão anterior.

O destino canônico é:

```text
%LOCALAPPDATA%\SRStudio\App\Graphics2Host
```

A pasta contém diretamente `SRGraphicsEngine2Host.exe`, `graphics2-host-runtime.json`, `_internal/...` e `graphics2-host-install.json`.

## Rollback

`rollback_host_install()` troca `Graphics2Host.previous` de volta para `Graphics2Host`. O runtime atual é removido somente depois que a versão anterior foi colocada de volta no destino.

## Segurança de ativação

A instalação do host não modifica `feature-flags.json`. Portanto instalar/atualizar o runtime não cria o botão experimental nem altera o editor padrão. A ativação continua dependendo de `graphics_engine_2`; a seleção automática de GPU depende de `graphics_engine_2_gpu`.

## Integração futura do installer/launcher

O instalador deve extrair/obter o bundle para uma área temporária e chamar o mesmo contrato de verificação/instalação. Não deve copiar DLLs Qt diretamente sobre uma instalação ativa, nem habilitar a feature flag antes de o runtime instalado passar na validação de versão e SHA-256.
