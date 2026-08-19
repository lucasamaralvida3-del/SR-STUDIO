# CHAT 3 — EDITOR G2 / UI DE PRODUÇÃO

## Missão desta rodada

Expor no host real do SR Graphics Engine 2 a importação PPTX já existente no backend, com contrato Canva → exportar como Microsoft PowerPoint (.pptx) → Studio G2.

## Isolamento

- Base de comparação: `g2/integration-beta`
- BASE SHA: `3e568f7717bb86978c58f50a5162fe44e27c4bd8`
- Branch isolada: `g2/chat3-import-ui-pptx`
- `g2/integration-beta` estava idêntica ao BASE SHA no início desta rodada.
- Nenhum merge foi executado.
- `main` e `stable` não foram alteradas.
- O ambiente desta conversa não expôs um checkout/worktree local do repositório; as alterações foram feitas somente na branch isolada pelo conector GitHub.

## Pipeline existente localizado

### EXISTING IMPORT ENTRY POINT

`src/srstudio/graphics2/import_bridge.py`

`GraphicsImportService.import_file(path, project_name=...)`

Este serviço usa `UnifiedImportPipeline` já existente, converte o `StudioProject` importado para `GraphicsDocument`, executa as passagens G2 de fidelidade/estrutura/semântica já existentes e retorna `GraphicsImportResult`.

### EXISTING CONTROLLER / BRIDGE

`src/srstudio/graphics2/qt_host.py`

`load_launch_context()` já usa `GraphicsImportService().import_file(...)` quando o source inicial não é `.srscene/.zip`.

O host real instancia `GraphicsSession`, `GraphicsCommandRouter` e anexa `qml/ProjectActions.qml` à janela principal.

### UI → IMPORT CALL PATH

`ProjectActions.qml`
→ `FileDialog(OpenFile, PowerPoint (*.pptx))`
→ `sceneBridge.dispatch({name: "import_pptx", path: ...})`
→ `GraphicsCommandRouter` com runtime `import_ui_runtime.py`
→ `GraphicsImportService.import_file(...)`
→ `UnifiedImportPipeline`
→ `GraphicsDocument`
→ substituição atômica de `GraphicsSession.document`
→ primeira página ativa
→ `sceneChanged`
→ toolbar/canvas/multipágina atualizados.

Nenhum segundo parser/importador foi criado.

## Implementação

### Botão

Label: `Importar PPTX / Canva`

Local: toolbar principal `ProjectActions.qml`, imediatamente antes de `Salvar`, próximo de `Recuperar`, PDF e PNG.

Tooltip:

`Importe um PowerPoint ou um projeto exportado do Canva em .pptx`

### File picker

- `QtQuick.Dialogs.FileDialog`
- `fileMode: FileDialog.OpenFile`
- filtro: `PowerPoint (*.pptx)`

### Estado durante importação

- flag `importingPptx` bloqueia cliques repetidos nos comandos principais;
- `BusyIndicator` também considera `importingPptx`;
- import é disparado por `Timer` de 1 ms após aceitar o picker para permitir a UI processar a mudança de estado antes da chamada síncrona existente;
- não foi introduzida nova arquitetura assíncrona.

### Sucesso

Após `GraphicsImportService` terminar:

- só então o documento atual é substituído;
- `active_page_id` é forçado para a primeira página importada;
- history e seleção anteriores são limpos;
- clipboard anterior é limpo;
- integridade de IDs é recalculada;
- `changed=True` faz o host emitir `sceneChanged` e agendar autosave pelo fluxo existente.

### Falha

- o documento/canvas anterior não é substituído antes de o importador terminar;
- mensagem amigável: `Não foi possível importar este arquivo PPTX.`;
- `MessageDialog` mostra somente a mensagem amigável;
- detalhe técnico permanece apenas no resultado interno do comando;
- aplicação não deve fechar por falha de importação.

## Arquivos alterados

### Production files

- `src/srstudio/graphics2/__init__.py`
- `src/srstudio/graphics2/import_ui_runtime.py` (novo)
- `src/srstudio/graphics2/qml/ProjectActions.qml`

### Test files

- `tests/test_graphics2_import_ui.py` (novo)

Nenhum arquivo de renderer, ImageInspector, Image Database, ProductCards, matching, export engine ou Canva corpus foi alterado.

## Candidatos separados não misturados

- keyboard focus `b592cb71bef3bd71596afadb6dee85db122279e2`: **NÃO presente no BASE**; é descendente separado do BASE e não foi misturado nesta branch.
- text auto-wrap `030fe9d5dc5798930c6ebedca41086980beffc61`: **NÃO presente no BASE**; é descendente separado do BASE e não foi misturado nesta branch.
- ImageInspector: nenhuma alteração.

## PPTX real localizado para teste

Arquivo da biblioteca do usuário:

`OFERTAS QUINTA FILÉ NOVO(1).pptx`

- tamanho: 5.510.518 bytes
- pacote OOXML contém 3 slides

O arquivo foi materializado nesta sessão para inspeção estrutural. O ambiente atual, porém, não possui checkout executável do SR-STUDIO nem host Windows/PySide6 da beta; portanto o import real pelo host não foi certificado aqui e não deve ser marcado como PASS.

## Testes / contratos implementados

`tests/test_graphics2_import_ui.py` cobre:

1. botão/tooltip visíveis no QML;
2. FileDialog `OpenFile`;
3. filtro `PowerPoint (*.pptx)`;
4. chamada `import_pptx` pela UI;
5. uso de `GraphicsImportService` existente;
6. promoção do documento somente após sucesso;
7. primeira página ativa;
8. page count do documento importado;
9. history/seleção limpos;
10. falha preserva o canvas anterior;
11. mensagem amigável de erro;
12. extensão diferente de `.pptx` é rejeitada antes do pipeline.

Validação de sintaxe feita nesta sessão para `import_ui_runtime.py`: PASS via `py_compile`/AST local do conteúdo novo.

Não existe workflow/check observável associado ao candidate commit no conector desta sessão. Não registrar suíte como verde sem execução objetiva.

## Gate manual/Windows obrigatório pendente

Ainda precisa ser executado no host real da beta Windows:

- botão visível;
- picker abre;
- PPTX real importado;
- 3 páginas aparecem para o arquivo acima;
- primeira página renderiza;
- navegação multipágina;
- selecionar/mover elemento;
- editar texto;
- salvar `.srscene`;
- reabrir;
- exportar PNG;
- exportar PDF;
- regressões Graphics2/editor/import/Qt-QML.

## Estado atual

P0 conhecido introduzido por esta mudança: 0.

P1 da missão: implementação presente, **certificação Windows pendente**.

READY FOR NEW WINDOWS BETA: **NO** até o gate Windows real e as suítes afetadas passarem.

MERGE: **NO**.
