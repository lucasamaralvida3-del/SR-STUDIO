# G2 Continuous Progress — SR Studio de Encartes

Atualizado: 2026-08-18

## Escopo obrigatório

**O produto desta missão é exclusivamente o NOVO STUDIO DE ENCARTES G2.**

Inclui SR Graphics Engine 2, SR Scene 2, editor Qt/QML G2, importação PPTX/Canva do Studio, Office Layout usado pelo G2, renderer G2, ProductCards, PriceBlocks, Smart Slots, bindings, multipágina, persistência, autosave/recovery, export, build/release e QA do G2.

O **Gerador de Cartazes legado é outro produto e não faz parte do desenvolvimento desta rodada**. Artefatos provenientes de sistemas antigos só podem ser usados como fixtures estáticas, referências de compatibilidade ou regression gates compartilhados. Eles não autorizam executar, corrigir ou evoluir o Gerador de Cartazes.

Os oito Golden Masters históricos `CARTAZ_VENDA`, `SEGUNDA_DA_LIMPEZA*`, `CLUBE_EXCLUSIVO*` e `ATACADO` pertencem exclusivamente ao Gerador de Cartazes. Eles **não são gate de aceitação, fidelidade ou Beta do Studio de Encartes G2**. Seus scores históricos não devem ser usados para classificar o G2.

CHAT 8 / Image Database continua isolado e não está incluído nesta integração.

## Estado integrado

- Branch: `g2/integration-beta`
- HEAD funcional validado: `d14dc5bed4bf4f7402f4668eb66a63823f48a35a`
- CHAT 1: integrado
- CHAT 2: integrado
- CHAT 3: integrado semanticamente e validado
- CHAT 4: integrado
- CHAT 5: integrado e PASS
- CHAT 6: integrado e PASS
- CHAT 8: **não integrado**
- `main` / `stable`: não alteradas

## Auditoria de escopo da integração

Comparação auditada: `15dbce6742066783c46db5599926f359cd125493..d14dc5bed4bf4f7402f4668eb66a63823f48a35a`.

Classificação dos arquivos alterados:

### G2

Todos os arquivos nestes grupos são propriedade direta do G2:

- `.github/workflows/g2-*.yml`
- `build/build_graphics2_host.py`
- `build/graphics2_host_entry.py`
- `build/package_graphics2_component.py`
- `src/srstudio/graphics2/**`
- `tests/test_graphics2_*.py`
- `tests/benchmark_graphics2_*.py`
- `tools/g2_*.py`
- documentação `docs/parallel/CHAT*_...` referente às missões G2

Isso cobre editor, renderer, import adapters G2, Product System, save/load, autosave/recovery, export, fidelity tooling, release engineering, E2E e performance.

### Infraestrutura compartilhada necessária ao G2

- `pyproject.toml` — entrypoints/dependências do Graphics2
- `src/srstudio/diagnostics/crash_guard.py` — crash safety utilizada pelo entrypoint G2
- `src/srstudio/importers/pptx/package_order.py` — infraestrutura OOXML/PPTX consumida pelo pipeline G2
- `src/srstudio/importers/pptx/reader.py` — reader compartilhado consumido pelo importador G2
- `tests/test_pptx_presentation_order.py` — regression gate do reader compartilhado

Essas alterações só são aceitas porque são necessárias ao G2 e passaram regressão. O objetivo não é melhorar o produto legado.

### LEGACY

**Nenhum arquivo exclusivamente do Gerador de Cartazes legado foi modificado no delta integrado.**

Não foram alterados módulos do gerador antigo, UI antiga, exportadores antigos ou lógica funcional exclusiva de `CARTAZ_VENDA`, `SEGUNDA_DA_LIMPEZA`, `CLUBE_EXCLUSIVO`, `ATACADO` e equivalentes.

O probe de CI criado para tentar transportar o corpus dos oito Golden Masters errados foi encerrado **sem merge** após a correção de escopo. Nenhum código funcional entrou por esse probe.

## Readiness funcional — estado real

O HEAD funcional `d14dc5b...` está verde nos gates do Studio:

| Área | Estado |
|---|---|
| Startup | PASS |
| Linux | PASS |
| Windows/Qt | PASS |
| Build/Release | PASS |
| Editor G2 | PASS |
| Import PPTX/Canva G2 | PASS |
| Renderer G2 | PASS |
| Save/Load | PASS |
| Round-trip SR Scene 2 | PASS |
| Autosave | PASS |
| Recovery | PASS |
| Multipágina | PASS |
| ProductCards | PASS |
| PriceBlocks | PASS |
| Smart Slots | PASS |
| Bindings | PASS |
| PNG | PASS |
| JPEG | PASS |
| PDF single-page | PASS |
| PDF multipage | PASS |
| E2E | PASS |
| Regression G2 | PASS |
| Performance smoke | PASS |
| Crash safety | PASS |

### Evidência CHAT 5 / QA

- Linux focado: 34/34 PASS
- Windows/Qt focado: 60/60 PASS
- long-run Linux de 30 ciclos save/load: crescimento RSS observado ~0,15 MB
- Windows long-run/harness: crescimento RSS observado 0 MB nessa execução
- PNG Windows: mediana observada ~54 ms
- PDF multipágina de 10 páginas: ~21,6 ms por iteração no harness reportado

### Evidência CHAT 6 / export

- Linux: PASS
- Windows/Qt: PASS
- PNG/JPEG/PDF/batch/repeat/path/error handling: PASS
- Windows: 49 testes do contrato de export + regressão do renderer PASS
- frozen build / instalação / rollback: PASS

## Gate visual correto do Studio de Encartes G2

O gate visual oficial do G2 é o laboratório em `visual-fidelity/`, cujo fluxo é:

1. preservar exportação oficial do Canva/PowerPoint;
2. importar o PPTX real no SR Graphics Engine 2;
3. produzir SR Scene 2;
4. renderizar a página pelo `qt_renderer` G2;
5. comparar com a referência estática;
6. executar triage/impact sem alterar baseline para obter verde.

O caso real versionado atualmente é:

- `visual-fidelity/quinta-file-13-08-2026.json`
- fonte esperada: `OFERTAS QUINTA FILÉ NOVO (1).pptx`
- SHA esperado: `7c45cfa205c7e14af69e41c8d63b1c6a9d1a06df3cf9d0131ed612029884e536`
- quatro referências Canva oficiais, slides 12–15
- dimensões esperadas por referência: 1229×1536

Testes/tooling que pertencem realmente ao gate visual G2:

- `tests/test_graphics2_reference_suite.py`
- `tests/test_graphics2_fidelity_corpus.py`
- `tests/test_graphics2_fidelity_impact.py`
- `tests/test_graphics2_qt_renderer_font_weight.py`
- `tests/test_graphics2_qt_renderer_group_opacity.py`
- `tests/test_graphics2_qt_renderer_transparency.py`
- `tests/test_graphics2_pptx_shape_visual.py`
- `tests/test_graphics2_pptx_source_crop.py`
- `tests/test_graphics2_pptx_group_member_transform.py`
- `tests/test_graphics2_pptx_text_content_pipeline.py`
- `tests/test_graphics2_pptx_text_content_recovery.py`
- `src/srstudio/graphics2/reference_suite.py`
- `src/srstudio/graphics2/fidelity_corpus.py`
- `src/srstudio/graphics2/fidelity_impact.py`

### Estado do corpus visual G2 nesta auditoria

O manifesto correto foi localizado, e o PPTX de mesmo nome existente na Biblioteca foi auditado por SHA antes de qualquer comparação.

As cópias encontradas atualmente têm SHA:

- `OFERTAS QUINTA FILÉ NOVO(1).pptx`: `8f57f0518976c62cd88bc460eeda3df4b7eaa97d8be3e46ecbfac828af3fcf42`
- `OFERTAS QUINTA FILÉ NOVO.pptx`: `0353b8e2848eb6019c970ae6c83610ecb821d66d29a2f8faff80ee416b1f76f8`

Nenhuma delas corresponde ao SHA `7c45cf...` exigido pelo manifesto. As quatro imagens oficiais `1000255371.jpg` a `1000255374.jpg` também não foram recuperadas como conjunto hashado nesta execução.

Portanto, **não foi executado um score visual falso com arquivos homônimos**. O gate existe; falta recolocar o corpus privado exato para a medição quantitativa oficial.

Os scores históricos de 83–93% dos oito casos do Gerador de Cartazes estão explicitamente excluídos desta avaliação.

## P0 / P1 / P2 / P3 — somente G2

### P0

**0 conhecidos.**

Não há crash, corrupção, perda de projeto, startup impossível ou export impossível conhecido nos gates atuais do Studio.

### P1

**0 funcionais impeditivos conhecidos.**

Os gates de editor/import/persistência/autosave/recovery/Product System/export estão verdes em Linux e Windows/Qt.

### P2

**1 — evidência quantitativa do gate visual real do G2 ainda pendente.**

O laboratório e manifesto existem, mas o corpus privado exato (PPTX hashado + quatro referências Canva hashadas) precisa ser restaurado antes de medir fidelidade. Isso é uma lacuna de validação visual, não uma falha funcional conhecida.

### P3

**0 classificados nesta auditoria.**

Polimentos futuros podem surgir em uso real, mas não há item P3 aberto confirmado por esta rodada.

## Classificação

### Functional readiness

**BETA FUNCIONAL: SIM.**

Há evidência Linux + Windows/Qt + build/release + editor + import + persistence + autosave/recovery + Product System + export + E2E + performance, sem P0 ou P1 funcional conhecido.

### Visual fidelity

**NÃO CLASSIFICADA quantitativamente nesta rodada.**

Não usar os oito Golden Masters do Gerador de Cartazes para essa decisão. A aprovação visual deverá vir do corpus próprio do Studio em `visual-fidelity/` e de novos projetos Canva/PPTX reais pertencentes ao fluxo de encartes.

### Release status

O Studio pode ser tratado como **Beta funcional do G2**, mas a aprovação de fidelidade visual para produção deve aguardar a execução do gate visual próprio com as fixtures privadas corretas.

## Próxima prioridade exclusivamente do Studio

1. recuperar o PPTX exatamente hashado `7c45cf...` e as quatro referências Canva com os hashes do manifesto, **ou** criar um novo manifesto versionado para um projeto de Encarte G2 atual com exportações oficiais correspondentes;
2. executar `reference_suite` somente sobre o G2;
3. registrar score/pixel-pass/changed-area por página e triage;
4. ampliar o corpus próprio com ao menos um encarte multipágina real, crop/rotação/transparência/grupos/camadas, fontes não instaladas e ProductCards/PriceBlocks;
5. manter Gerador de Cartazes e seus Golden Masters fora do critério de aceitação do Studio.
