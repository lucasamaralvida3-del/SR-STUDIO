# CHAT 7 — Build, Release Engineering, Packaging e Integração Segura

## Fase atual

**FASE A somente.** Nenhum merge/cherry-pick de branch paralela foi executado. `main` e `stable` não foram alteradas.

## BASE_SHA e isolamento

- `BASE_SHA`: `15dbce6742066783c46db5599926f359cd125493`
- Branch: `g2/parallel-release-engineering`
- Worktree solicitado: `../SR-STUDIO-g2-release-engineering`
- Nesta execução remota, checkout/worktree local não ficou disponível porque o ambiente não resolve `github.com` por rede direta. O trabalho foi feito exclusivamente na branch remota isolada pelo conector GitHub.
- Branches paralelas observadas: `g2/parallel-render-fidelity`, `g2/parallel-import-office`, `g2/parallel-editor-production`, `g2/parallel-product-system`, `g2/parallel-qa-performance`, `g2/parallel-export-output`, `g2/parallel-release-engineering`.
- O `BASE_SHA` é o merge-base comum confirmado entre CHAT 1 e CHAT 2 no início desta missão e contém `AGENTS.md`, `docs/SR_STUDIO_NEXT_ARCHITECTURE.md` e `docs/G2_CONTINUOUS_PROGRESS.md`.

## Ambiente e baseline

- Python suportado pelo projeto: `>=3.11`.
- Dependência Qt declarada: `PySide6>=6.8,<7` no extra `graphics2`.
- Toolchain de build: `PyInstaller>=6.21,<7` no extra `graphics2-build`.
- Build Windows existente: `build/build_graphics2_host.py`, bundle `onedir`, `--windowed`, `--noupx`, `--collect-all PySide6`, `--collect-data srstudio`.
- Integridade do bundle existente: `graphics2-host-runtime.json` com SHA-256 por arquivo.
- QML de runtime já declarado em `package-data`: `graphics2/qml/*.qml`.
- Entry point legado anterior: `srstudio.graphics2.qt_host:main`.
- Entry point de release adotado nesta branch: `srstudio.graphics2.entrypoint:main`.

## Auditoria de dependências

Dependências diretas observadas no caminho G2 revisado:

- Qt/QML/render: `PySide6` — declarado no extra `graphics2` e no extra de build.
- Excel: `openpyxl` — declarado.
- imagens: `Pillow` — declarado.
- PDF e baseline: `pypdf`, `pypdfium2` — declarados.
- PPTX do G2 usa leitor OOXML/ZIP próprio no caminho auditado, sem exigir `python-pptx` para startup.

Não foi feito upgrade grande de dependências.

## Problemas encontrados

### P1 — CI do host congelado não cobria a branch paralela

O workflow histórico `graphics-engine-2-host-build.yml` disparava por `push` somente em `feature/sr-graphics-engine-2`. Assim, alterações de release na branch CHAT 7 poderiam ficar sem build/smoke congelado automático.

**Ação:** criado workflow dedicado `g2-release-engineering.yml` para `g2/parallel-release-engineering` e já preparado para a futura `g2/integration-beta`, sem alterar fluxo oficial de release/main/stable.

### P1 — diagnóstico de startup insuficiente no entrypoint de produção

`qt_host.main()` convertia exceções graves em mensagem curta no stderr. No executável `--windowed`, esse stderr pode não ser visível e o traceback não ficava persistido.

**Ação:** adicionado wrapper `graphics2.entrypoint` com log rotativo e `CrashGuard`, registrando versão, timestamp, traceback, ação, módulo e projeto quando disponível.

### P1 — smoke do executável congelado cobria apenas probe gráfico

O build existente validava integridade do bundle e backend Qt, mas não exercitava round-trip SR Scene + PNG + PDF no host empacotado.

**Ação:** adicionado `release_smoke` e suporte `--release-smoke` ao entrypoint congelado. O smoke cria projeto simples, salva `.srscene`, reabre, exporta PNG/PDF, valida QML/plugins Qt e gera relatório JSON com hashes.

### P1 evitado — diagnóstico não pode bloquear startup

O primeiro wrapper poderia falhar se o diretório preferido de diagnóstico não fosse gravável. O caminho foi endurecido para tentar o diretório configurado/home e, em caso de erro, cair para a pasta temporária do sistema.

### Dependência externa — JPEG

O baseline desta branch possui PNG/PDF no renderer G2. JPEG pertence ao CHAT 6 (`g2/parallel-export-output`). O CHAT 7 não implementou JPEG para não invadir propriedade de outro agente. A futura integração deve exigir evidência do CHAT 6 antes do RC.

## Startup e paths

- QML é localizado a partir de `Path(__file__).with_name("qml")`, não do CWD.
- Cache runtime e autosave usam `Path.home()`/diretórios configuráveis, não o CWD.
- O novo diretório de diagnóstico usa `~/.srstudio5/diagnostics-g2` ou `SR_STUDIO_G2_DIAGNOSTICS_ROOT`, com fallback para `%TEMP%/SRStudio/diagnostics-g2` (ou equivalente da plataforma).
- O smoke de CI é definido para executar de um diretório diferente do checkout e detectar dependência acidental de working directory.
- O host instalado continua validado por manifesto de runtime e versão do Engine antes de ser aceito pelo bridge.

## Logging / crash report

Arquivo padrão:

`~/.srstudio5/diagnostics-g2/graphics2.log`

Crash marker:

`~/.srstudio5/diagnostics-g2/last_crash.json`

Campos persistidos: versão, timestamp UTC, tipo da exceção, mensagem, traceback, projeto/arquivo quando conhecido, ação e módulo.

## Caminhos de execução

Desenvolvimento:

```bash
python -m pip install -e '.[dev,graphics2]'
sr-graphics-engine-2
```

Diagnóstico GPU:

```bash
sr-graphics-engine-2 --graphics-api software --probe-graphics-api
```

Release smoke em ambiente Python:

```bash
sr-graphics2-release-smoke --output-dir ./release-smoke
```

Build Windows:

```bash
python -m pip install -e '.[dev,graphics2-build]'
python build/build_graphics2_host.py --output ./dist/graphics2-host
```

Smoke do executável congelado:

```powershell
SRGraphicsEngine2Host.exe --release-smoke --output-dir C:\temp\g2-release-smoke
```

## Artefatos esperados do smoke

- `release-smoke.srscene`
- `release-smoke.png`
- `release-smoke.pdf`
- `release-smoke.json`
- `graphics2-host-manifest.json`
- `graphics2-host-runtime.json`
- bundle `SRGraphicsEngine2Host/`

## Checklist Release Candidate

| Área | Gate Fase A | Dono/observação |
|---|---|---|
| STARTUP | CI clean + frozen probe + CWD independente | CHAT 7 |
| PROJECT NEW | release smoke cria SR Scene 2 mínima | CHAT 7 |
| LOAD | smoke reabre `.srscene` | CHAT 7 |
| SAVE | smoke grava pacote portátil | CHAT 7 usando contrato existente |
| AUTOSAVE | pendente integração | CHAT 3 |
| RECOVERY | pendente integração | CHAT 3 |
| PPTX IMPORT | pendente integração | CHAT 2 |
| EDITOR | pendente integração | CHAT 3 |
| PRODUCTCARD | pendente integração | CHAT 4 |
| PRICEBLOCK | pendente integração | CHAT 4 |
| SMART SLOT | pendente integração | CHAT 4 |
| MULTIPAGE | pendente integração | CHAT 3 |
| PNG | smoke estrutural; fidelidade/produção pertence CHAT 6/1 | CHAT 7 + CHAT 6/1 |
| JPEG | pendente | CHAT 6 |
| PDF | smoke estrutural; pipeline final pertence CHAT 6 | CHAT 7 + CHAT 6 |
| PERFORMANCE | pendente | CHAT 5 |
| CRASH | log + crash marker | CHAT 7 |
| SAFETY | integridade SHA-256 + sem main/stable | CHAT 7 |

## Validação executada nesta sessão

- Leitura de `AGENTS.md`, arquitetura e progresso G2 concluída antes das alterações.
- `BASE_SHA` confirmado e branch de CHAT 7 criada/reutilizada sem tocar em `main`/`stable`.
- Diff da branch contra o `BASE_SHA` revisado e limitado ao escopo CHAT 7.
- Busca por referências ao entrypoint antigo (`from srstudio.graphics2.qt_host import main` / `srstudio.graphics2.qt_host:main`) não encontrou referências residuais no índice disponível.
- Checagem estática local dos novos módulos `entrypoint.py` e `release_smoke.py` via `python -m py_compile`: **PASS**.
- O ambiente local deste chat não possui `PySide6` e não consegue resolver `github.com` por rede direta; portanto o host Qt não pôde ser executado localmente.
- Workflow `G2 Release Engineering` foi criado para executar ambiente limpo Linux + build/smoke congelado Windows. O conector desta sessão não expôs um run de `push` associado aos commits (o método disponível lista runs de PR), portanto **não há evidência suficiente para marcar o frozen smoke como PASS nesta sessão**.

## Status Fase A ao encerrar esta rodada

| Área | Resultado | Bloqueador/nota |
|---|---|---|
| Build scripts | PASS WITH KNOWN P2 | contrato auditado; execução completa depende do runner Windows |
| Startup paths | PASS WITH KNOWN P2 | paths independentes de CWD revisados; execução Qt real pendente no runner |
| Dependencies | PASS | dependências diretas auditadas/declaradas; sem upgrade grande |
| Logging | PASS | log rotativo + fallback de diretório |
| Crash diagnostics | PASS | versão/timestamp/traceback/ação/módulo/projeto |
| Portable package smoke | PASS WITH KNOWN P2 | lógica criada e sintaxe validada; execução Qt real pendente |
| Frozen Windows host | FAIL P1 (validation pending) | precisa de evidência real do workflow/runner antes de Beta utilizável |
| JPEG | FAIL P1 (external dependency) | propriedade do CHAT 6; não corrigido aqui |
| Integration | NOT STARTED | Fase B proibida nesta rodada |

## Commits Fase A

- `d21a25cc476e5b91bd5267e7f09680c4a8122a14` — enriquece crash diagnostics.
- `812a4610a5fa68b684c008b638dc950ecd37a724` — entrypoint de startup/release.
- `fe14cb4ebd63a102bb2dcb5583f8337fa1296055` — release smoke.
- `eafe0139812269319eb9b41219782fa2324f5ffd` — host congelado usa entrypoint endurecido.
- `2f4b96c664dde4a202d0f02f0ba1dcef7bf43e50` — comandos de startup/smoke no `pyproject.toml`.
- `58be3d988a57770f06ffd43832e29c4449c58ba3` — contrato de teste do host atualizado.
- `e501ada01440feeec6c85475e165d84636a8221d` — testes release diagnostics/smoke.
- `3455a79cf6d9db96c242d07c2156fbaf927b0134` — documentação inicial CHAT 7.
- `49f24b42b39de4a883268905765911c7c0cecc9c` — workflow isolado de release engineering.
- `0f4382e0ffe4a10d5061d8923530662f659d597d` — gate preparado para integração e versão dinâmica.
- `9b0ff13efd4924335e8d85e8904daa1c26ae42a7` — fallback de diagnóstico para não bloquear startup.
- `8c87bb833c481e8cf63cc7cd3647a0b7e4532261` — teste do fallback de diagnóstico.

## Futura Fase B

Não iniciar até ordem explícita ou branches claramente prontas. Antes de integrar cada branch: ler o relatório daquele CHAT, identificar commits, contratos e dependências reais, então testar após cada merge/cherry-pick. Nunca usar `ours`/`theirs` cegamente e nunca integrar em `main`/`stable`.
