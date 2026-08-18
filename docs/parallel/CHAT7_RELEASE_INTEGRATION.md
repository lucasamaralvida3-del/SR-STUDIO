# CHAT 7 — Build, Release Engineering, Packaging e Integração Segura

## Fase atual

**FASE A somente.** A Fase B não foi iniciada.

- Nenhum merge/cherry-pick de branch paralela foi executado.
- `main` e `stable` não foram alteradas.
- Nenhum threshold, Golden Master ou teste funcional de outro CHAT foi relaxado.
- Nenhum release Beta/Stable foi publicado ou ativado.

## BASE_SHA e isolamento

- `BASE_SHA`: `15dbce6742066783c46db5599926f359cd125493`
- Branch: `g2/parallel-release-engineering`
- Worktree solicitado: `../SR-STUDIO-g2-release-engineering`
- O ambiente deste chat não conseguiu resolver `github.com` por rede direta para criar um checkout/worktree local. Para não fingir isolamento inexistente, todas as alterações foram feitas exclusivamente na branch remota isolada através do conector GitHub.
- Branches paralelas observadas: `g2/parallel-render-fidelity`, `g2/parallel-import-office`, `g2/parallel-editor-production`, `g2/parallel-product-system`, `g2/parallel-qa-performance`, `g2/parallel-export-output`, `g2/parallel-release-engineering`.
- Antes desta atualização documental, a comparação com o `BASE_SHA` mostrava **36 commits à frente, 0 atrás**, limitados a 16 arquivos de build/startup/diagnóstico/empacotamento/testes/documentação do CHAT 7.

## Documentos lidos antes das alterações

- `AGENTS.md`
- `docs/SR_STUDIO_NEXT_ARCHITECTURE.md`
- `docs/G2_CONTINUOUS_PROGRESS.md`

`docs/G2_CONTINUOUS_PROGRESS.md` não foi editado durante o trabalho paralelo.

## Ambiente e dependências

### Python

- Projeto: Python `>=3.11`.
- CI validada com Python 3.11 no Linux e Windows.

### Dependências Python auditadas no caminho G2

- Qt/QML/render: `PySide6>=6.8,<7` — declarado no extra `graphics2`.
- Build congelado: `PyInstaller>=6.21,<7` — declarado no extra `graphics2-build`.
- Excel: `openpyxl>=3.1.2` — declarado.
- Imagem: `Pillow>=10.0.0` — declarado.
- PDF/baseline: `pypdf>=4.0.0`, `pypdfium2>=4.30.0` — declarados.
- O leitor PPTX auditado no G2 usa OOXML/ZIP próprio e não exige `python-pptx` para o startup básico.

Nenhum upgrade grande foi feito.

### Dependência de sistema Linux encontrada por máquina limpa

No Ubuntu 24.04/runner, o primeiro smoke Qt falhou ao importar `PySide6.QtCore/QtGui` por ausência de `libEGL.so.1`.

A dependência de runtime foi tornada explícita no gate Linux:

```bash
sudo apt-get install -y --no-install-recommends libegl1
```

Após isso, import Qt, software backend, export e startup real do editor QML passaram.

## Caminho oficial de startup

Antes:

```text
sr-graphics-engine-2 -> srstudio.graphics2.qt_host:main
```

Agora:

```text
sr-graphics-engine-2 -> srstudio.graphics2.entrypoint:main -> qt_host
```

O executável PyInstaller e o fallback de desenvolvimento do `studio_bridge` usam o mesmo entrypoint endurecido.

### Comandos

Desenvolvimento:

```bash
python -m pip install -e '.[dev,graphics2]'
sr-graphics-engine-2
```

Versão sem abrir UI:

```bash
sr-graphics-engine-2 --version
sr-graphics-engine-2 -V
```

Probe gráfico:

```bash
sr-graphics-engine-2 --graphics-api software --probe-graphics-api
```

Release smoke:

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

## Paths e recursos de runtime

- QML é localizado relativamente a `__file__`, não ao CWD.
- `graphics2/qml/*.qml` permanece em `package-data`.
- O PyInstaller inclui `srstudio` data e módulos G2 necessários.
- Cache/autosave usam home/configuração específica, não o CWD.
- Diagnóstico usa `SR_STUDIO_G2_DIAGNOSTICS_ROOT` ou `~/.srstudio5/diagnostics-g2`, com fallback para a pasta temporária do sistema.
- O diretório de diagnóstico é testado por escrita real antes de ser aceito.
- O bridge aceita host empacotado apenas quando o runtime canônico possui manifesto íntegro e versão compatível.
- O gate roda os smokes fora do checkout para detectar dependência acidental do working directory.

## Logging e crash report

Log rotativo padrão:

```text
~/.srstudio5/diagnostics-g2/graphics2.log
```

Crash marker:

```text
~/.srstudio5/diagnostics-g2/last_crash.json
```

Informações persistidas:

- versão do SR Studio;
- versão do Graphics Engine 2;
- timestamp UTC;
- tipo da exceção;
- mensagem;
- traceback;
- ação em execução;
- módulo;
- projeto/arquivo quando conhecido e seguro.

## Release smoke v2

O smoke não verifica apenas presença de arquivos. Ele executa:

1. cria uma SR Scene 2 mínima;
2. salva `.srscene` portátil;
3. reabre o pacote;
4. exporta PNG;
5. exporta PDF;
6. valida diretórios de plugins Qt e imports QML;
7. inicializa backend `software`;
8. carrega o **`GraphicsEditor.qml` real** e suas ferramentas contextuais;
9. entra no event loop;
10. fecha automaticamente;
11. exige `editor_exit_code=0`;
12. grava `release-smoke.json` com ambiente, versões e SHA-256 dos artefatos.

Campos centrais do relatório atual:

```text
schema: srstudio/g2-release-smoke-2
ok: true
editor_qml_startup: true
editor_exit_code: 0
```

## Problemas P1 encontrados e corrigidos

### 1. CI do host não cobria a branch paralela

O workflow histórico do host estava ligado principalmente à branch antiga do Graphics2.

**Correção:** workflow dedicado `.github/workflows/g2-release-engineering.yml`, preparado para:

- `g2/parallel-release-engineering`;
- futura `g2/integration-beta`;
- validação por PR sem tocar em `main/stable`.

### 2. Startup grave não deixava diagnóstico persistente suficiente

**Correção:** entrypoint com logging rotativo + CrashGuard contextual.

### 3. Executável congelado só tinha probe gráfico, sem fluxo de arquivo

**Correção:** release smoke com save/load/PNG/PDF e, depois, startup real de QML.

### 4. Diagnóstico poderia bloquear startup se HOME/config estivesse sem permissão

**Correção:** fallback para temp e prova real de escrita.

### 5. Descritor de componente podia representar estado impossível

Estados agora rejeitados:

- `enabled=true` sem `url` nem `source`;
- `required=true` com `enabled=false`.

### 6. `keep_previous=False` podia destruir rollback cedo demais

**Correção:** `Graphics2Host.previous` só é descartado após o novo runtime passar pela validação final. Teste força falha pós-switch e confirma restauração do anterior.

### 7. Fallback de desenvolvimento contornava o entrypoint endurecido

**Correção:** `studio_bridge` usa `python -m srstudio.graphics2.entrypoint`, mantendo o mesmo diagnóstico de produção.

### 8. Dependência Linux EGL não estava explícita

**Correção:** `libegl1` tornou-se pré-requisito explícito do gate Linux e o smoke passou.

## P2 de empacotamento corrigido — bundle Qt excessivo

### Baseline anterior

O host congelado histórico usava:

```text
--collect-all PySide6
```

Evidência do primeiro artefato Windows verde:

- bundle: **720.960.686 bytes**;
- arquivos: **3.833**;
- componente ZIP: **273.625.789 bytes**;
- `Qt6WebEngineCore.dll` sozinho: ~205 MB;
- G2 não usa WebEngine.

### Caminho enxuto atual

O build agora declara somente os módulos Qt usados pelo host:

- `PySide6.QtCore`;
- `PySide6.QtGui`;
- `PySide6.QtQml`;
- `PySide6.QtQuick`.

Também exclui os módulos Python WebEngine e remove resíduos WebEngine copiados indiretamente pela árvore QML **após o COLLECT e antes do manifesto SHA-256**.

Uma checagem falha o build se qualquer caminho contendo `WebEngine` sobreviver.

### Resultado validado em Windows limpo

- bundle: **245.780.712 bytes**;
- arquivos totais: **2.884**;
- arquivos catalogados: **2.883/2.883 verificados**;
- componente ZIP: **100.122.203 bytes**;
- artefato Actions do gate: **99.018.265 bytes**;
- entradas WebEngine no artefato: **0**.

Redução contra o baseline:

- bundle: **-65,9%**;
- arquivos: **-24,8%**;
- componente ZIP: **-63,4%**.

A otimização só foi mantida porque o host enxuto passou o startup real do `GraphicsEditor.qml`, exports, instalação e rollback.

## Gate de máquina limpa

Workflow: `G2 Release Engineering`.

### Linux

Valida:

- `libegl1`/`libEGL.so.1`;
- Python limpo;
- PySide6/QtGui;
- contratos de release;
- CWD fora do checkout;
- save/load;
- PNG/PDF;
- backend software;
- `GraphicsEditor.qml` real;
- saída limpa.

### Windows

Valida:

1. Python limpo;
2. PyInstaller/PySide6;
3. testes de release/build/install/bridge/launcher;
4. smoke de desenvolvimento fora do checkout;
5. build onedir;
6. poda de WebEngine;
7. catálogo SHA-256 completo;
8. probe Qt congelado;
9. release smoke congelado com editor QML real;
10. componente ZIP ainda `enabled=false`/`required=false` em CI;
11. SHA-256 do ZIP;
12. instalação em `%LOCALAPPDATA%/SRStudio/App/Graphics2Host`;
13. descoberta pelo bridge;
14. smoke do host instalado;
15. segunda instalação;
16. criação de `.previous`;
17. rollback;
18. descoberta do runtime restaurado.

## Evidência CI real

### Linux — full QML

Run `32087996011`:

- ambiente limpo: PASS;
- `libegl1`: PASS;
- contratos: PASS;
- smoke fora do checkout: PASS;
- `GraphicsEditor.qml`: PASS;
- `editor_exit_code=0`: PASS;
- artefato Linux publicado.

Um run posterior ficou preso no próprio passo `apt` do runner; isso não revelou regressão de código. As mudanças posteriores relevantes são do empacotador Windows e os testes correspondentes passaram no Windows.

### Windows — bundle enxuto / HEAD funcional

Run `32088288753`, job `windows-frozen-release`:

- **46 testes PASS**;
- dev smoke fora do checkout: PASS;
- build PyInstaller enxuto: PASS;
- 5 itens WebEngine removidos: PASS;
- runtime `2.0.0-alpha.43`: **2.883/2.883** arquivos verificados;
- frozen GPU probe: PASS;
- frozen save/load/PNG/PDF: PASS;
- frozen `GraphicsEditor.qml`: PASS;
- `frozen=true`: PASS;
- componente ZIP + SHA: PASS;
- instalação canônica: PASS;
- bridge discovery: PASS;
- installed host smoke: PASS;
- segunda instalação + rollback: PASS;
- runtime restaurado encontrado novamente: PASS;
- artefato Windows publicado.

## PR de validação

Foi criado um PR **draft, validation-only, DO NOT MERGE** para tornar os runs `pull_request` observáveis pelo conector:

- PR #28;
- base: `g2/parallel-release-engineering`;
- head: `g2/chat7-release-ci-probe`;
- único conteúdo próprio: marcador `docs/parallel/CHAT7_CI_PROBE.md`;
- nenhuma mudança funcional própria;
- nunca deve ser mergeado.

Após coletar a evidência, o PR deve ser fechado sem merge; a branch pode permanecer para auditoria.

## Artefatos de release validados

- `release-smoke.srscene`;
- `release-smoke.png`;
- `release-smoke.pdf`;
- `release-smoke.json`;
- `graphics2-host-manifest.json`;
- `graphics2-host-runtime.json`;
- `graphics2-host-component.json`;
- `graphics2-host-component.zip`;
- `graphics2-host-install.json`;
- bundle `SRGraphicsEngine2Host/`.

## Distribuição / instalador

Dois layouts são suportados pelo bridge:

1. `Graphics2Host` ao lado do Desktop congelado;
2. runtime canônico separado em `%LOCALAPPDATA%/SRStudio/App/Graphics2Host`.

A arquitetura atual mantém Qt em subprocesso separado do Desktop/Tk. A instalação do host não ativa feature flag automaticamente.

### Dependência futura de integração

Publishers históricos também conseguem embutir `Graphics2Host` dentro do bundle Desktop. Na Fase B, escolher conscientemente um contrato de distribuição por canal:

- host embutido no bundle; ou
- componente separado/atualizável pelo launcher.

Não publicar os dois de forma incoerente.

## Checklist Release Candidate — propriedade CHAT 7 / dependências externas

| Área | Resultado atual | Bloqueador / dono |
|---|---|---|
| STARTUP | PASS | CHAT 7 |
| PROJECT NEW | PASS | smoke CHAT 7 |
| LOAD `.srscene` | PASS | smoke CHAT 7 |
| SAVE `.srscene` | PASS | smoke CHAT 7 |
| AUTOSAVE | PENDENTE INTEGRAÇÃO | CHAT 3 |
| RECOVERY | PENDENTE INTEGRAÇÃO | CHAT 3 |
| PPTX IMPORT | PENDENTE INTEGRAÇÃO | CHAT 2 |
| EDITOR | PASS STARTUP ONLY | funcionalidade completa: CHAT 3 |
| PRODUCTCARD | PENDENTE INTEGRAÇÃO | CHAT 4 |
| PRICEBLOCK | PENDENTE INTEGRAÇÃO | CHAT 4 |
| SMART SLOT | PENDENTE INTEGRAÇÃO | CHAT 4 |
| MULTIPAGE | PENDENTE INTEGRAÇÃO | CHAT 3 |
| PNG | PASS estrutural/smoke | pipeline final: CHAT 6; fidelidade: CHAT 1 |
| JPEG | PENDENTE / FAIL P1 EXTERNO | CHAT 6 |
| PDF | PASS estrutural/smoke | pipeline final: CHAT 6 |
| PERFORMANCE | PENDENTE INTEGRAÇÃO | CHAT 5 |
| BUILD | PASS | CHAT 7 |
| STARTUP FROZEN | PASS | CHAT 7 |
| STARTUP INSTALADO | PASS | CHAT 7 |
| LOGGING | PASS | CHAT 7 |
| CRASH DIAGNOSTICS | PASS | CHAT 7 |
| PACKAGE INTEGRITY | PASS | CHAT 7 |
| INSTALL / ROLLBACK | PASS | CHAT 7 |
| SAFETY | PASS | CHAT 7 |
| INTEGRAÇÃO | NOT STARTED | Fase B proibida nesta rodada |

## Status de severidade da Fase A

- P0 abertos no escopo CHAT 7: **0**.
- P1 abertos no escopo próprio CHAT 7: **0 conhecidos após os gates acima**.
- P1 externo conhecido para o RC global: **JPEG / CHAT 6**, até evidência da branch de exportação.
- P2: escolher política final de distribuição do host na integração; manter observabilidade de tamanho do bundle.

## Commits relevantes desta Fase A

### Startup / diagnóstico

- `d21a25cc476e5b91bd5267e7f09680c4a8122a14` — contexto extra no CrashGuard.
- `812a4610a5fa68b684c008b638dc950ecd37a724` — entrypoint endurecido inicial.
- `9b0ff13efd4924335e8d85e8904daa1c26ae42a7` — fallback de diagnóstico.
- `92c5b1d5cdaf2cb4ef4ef684289fffe7d46dd38e` — `--version`/`-V`.
- `4f5a7daf2be8aeb21db148398c3ad65499a5eb37` — diretório de diagnóstico realmente gravável.
- `e1d85656b722760a065e525664455246181fbbfd` — bridge dev usa entrypoint endurecido.

### Smoke / build

- `fe14cb4ebd63a102bb2dcb5583f8337fa1296055` — release smoke inicial.
- `be81ac0647f691cac6c8c3c5a33e82b05d891f64` — startup real do editor QML no smoke.
- `eafe0139812269319eb9b41219782fa2324f5ffd` — frozen host usa entrypoint endurecido.
- `6112ccdb4887eec44c0ce73f3955325cd1307c3b` — primeira redução do collect PySide6.
- `234765a117165852a864478aa67da4eff244d5d6` — gate contra payload WebEngine inesperado.
- HEAD funcional antes desta atualização documental: `110c386e765dd6c509ad417dff55ca8ef04db806` — poda seletiva WebEngine + regressões de build, validada no run Windows `32088288753`.

### Empacotamento / instalação

- `55931fda9ae470898fe05294353530b55a943d00` — validação semântica de descritor.
- `ef46b0cbbd326e2fc7ae220afc3585b599a440a4` — preserva rollback até validação final.

### CI

- `49f24b42b39de4a883268905765911c7c0cecc9c` — gate CHAT 7 inicial.
- `ca448f7f062f131fbe6d219aa63c0e7f1c2e1c88` — ZIP/install/discovery/rollback no gate.
- `9ca168ee4cac548294b1d141509a6e9f3a65a862` — validação isolada por PR.
- `76ab689d02f5fc74b83efa5eb723bcf0813db197` — dependência Linux `libegl1` explícita.

## Fase B — NÃO INICIADA

Quando houver ordem explícita ou as branches estiverem claramente prontas:

1. criar/reutilizar `g2/integration-beta`;
2. ler cada `docs/parallel/CHAT*_*.md`;
3. identificar commits e contratos alterados;
4. mapear dependências antes de escolher ordem;
5. integrar sem `ours/theirs` cego;
6. testar após cada integração;
7. ao final executar suíte G2, Golden Masters, E2E, save/load, multipage, products, PNG/JPEG/PDF e smoke startup;
8. produzir auditoria final `ÁREA | RESULTADO | BLOQUEADORES`.

Nenhuma ação desta Fase B foi executada nesta sessão.
