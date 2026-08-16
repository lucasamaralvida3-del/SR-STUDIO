# SR Graphics Engine 2 — Host Qt isolado

O Engine 2 foi desenhado para abrir em um processo Qt separado do shell Tk do SR Studio. O bundle de distribuição do host usa PyInstaller em modo **onedir**.

## Dependências de build

No Windows:

```powershell
python -m pip install -e ".[graphics2-build]"
```

O extra instala PySide6 e PyInstaller usados somente para gerar o host.

## Gerar o bundle

```powershell
python build/build_graphics2_host.py
```

Saída padrão:

```text
dist/graphics2-host/
  graphics2-host-manifest.json
  SRGraphicsEngine2Host/
    SRGraphicsEngine2Host.exe
    _internal/...
```

Para validar apenas os argumentos sem compilar:

```powershell
python build/build_graphics2_host.py --print-args
```

Para um bundle com console de diagnóstico:

```powershell
python build/build_graphics2_host.py --console
```

## Contrato do build

O builder:

- usa `--onedir` e `--windowed` no bundle de produção;
- desativa UPX;
- coleta PySide6, plugins/bibliotecas Qt e dados do pacote `srstudio`;
- inclui submódulos de `srstudio.graphics2`;
- produz `graphics2-host-manifest.json` com versão do Engine, plataforma, arquitetura, caminho do executável, SHA-256, quantidade de arquivos e tamanho total.

O build Windows deve ser executado no Windows. Não é tratado como cross-compilation.

## Descoberta pelo Studio Bridge

A ponte procura o host nesta ordem lógica:

1. caminho explícito em `SR_GRAPHICS_ENGINE_2_HOST`;
2. pasta `Graphics2Host` próxima ao executável atual;
3. pasta `Graphics2Host` próxima ao app/repositório;
4. `%LOCALAPPDATA%\SRStudio\App\Graphics2Host\SRGraphicsEngine2Host.exe`.

Se nenhum host empacotado existir e o programa estiver em ambiente de desenvolvimento, a ponte pode usar:

```text
<python atual> -m srstudio.graphics2.qt_host
```

Em build congelado, a ausência do host separado é tratada como erro controlado. O Engine 2 não é carregado dentro do processo Tk.

## Feature flags

O bundle não é iniciado automaticamente. A ponte continua protegida por:

```text
graphics_engine_2 = false
graphics_engine_2_gpu = false
```

A primeira flag libera o modo experimental; a segunda deixa o Qt escolher o backend acelerado (`auto`). Sem a flag GPU, o modo experimental usa `software`.

## Próxima etapa do instalador

O instalador/launcher deverá distribuir a pasta `SRGraphicsEngine2Host` para `%LOCALAPPDATA%\SRStudio\App\Graphics2Host` e validar o manifesto/SHA antes de disponibilizar a feature flag. Essa integração só deve entrar no canal de teste até o Production Gate real ser aprovado.
