# Arquitetura do SR Studio Next

## Decisão

O SR Graphics Engine 2.0 é o Studio de Encartes principal da próxima geração. A Beta 7.29 Professional permanece preservada como baseline de compatibilidade e fallback, sem substituir o novo motor gráfico.

## Fluxo principal

```text
Beta 7.29
    | compatibilidade
    v
SR Studio Core
    v
SR Graphics Engine 2
    v
SR Scene 2
    v
Command Router
    v
Qt/QML Editor
    v
Renderer
    v
PDF/PNG
```

`SR Scene 2` é o modelo canônico. UI, importadores, automações e futura SR IA devem solicitar mudanças pelo `Command Router`, preservando validação, transações e undo/redo. Preview e renderer devem interpretar a mesma cena e os mesmos contratos semânticos.

## Importação e produtos

```text
Excel/PPTX
    v
Import Pipeline
    v
SR Scene / Product Model

Banco de produtos
    v
ProductCards / Smart Slots
```

Os importadores podem reutilizar os componentes maduros do SR Studio, mas o resultado visual futuro deve ser normalizado em SR Scene 2. Produtos devem atravessar uma interface estável e preencher ProductCards, PriceBlocks e Smart Slots sem acoplamento ao widget desktop.

## SR IA futura

```text
SR IA futura
    v
proposta estruturada + validação + preview/diff
    v
Command Router
    v
SR Scene
```

A SR IA não recebe acesso de escrita direta à cena. Toda alteração continua auditável, validável e reversível pelo histórico transacional.

## Limites para evolução híbrida

- O desktop continua responsável pelo shell, compatibilidade local e integração gradual.
- SR Scene e comandos permanecem serializáveis e versionados.
- Assets usam ID/URI/hash, com resolução por adaptadores.
- Banco de produtos fica atrás de uma interface substituível.
- Importação, renderização e outras operações pesadas evoluem como jobs assíncronos sobre snapshots.
- Adaptadores locais e uma futura API cloud compartilham contratos, não widgets nem caminhos de arquivos.

Esta integração não implementa cloud, novas ferramentas gráficas, nova SR IA, novos modelos ou grandes mudanças de UI.
