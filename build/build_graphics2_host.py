from __future__ import annotations

"""Build reprodutível do host Qt separado do SR Graphics Engine 2.

O Studio principal usa Tk. Este build empacota somente o host Qt Quick em um
bundle onedir para que o launcher opcional possa iniciar outro processo sem
carregar Qt dentro do processo Tk. O modo onedir evita extração temporária a
cada abertura e mantém DLLs/plugins Qt explícitos para diagnóstico/reparo.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json
import os
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ENTRY = ROOT / "build" / "graphics2_host_entry.py"
DEFAULT_DIST = ROOT / "dist" / "graphics2-host"
HOST_NAME = "SRGraphicsEngine2Host"

# PySide6 6.11 pode carregar, via --collect-all, diretórios intermediários do
# build do Qt (objetos .obj). Eles não participam do runtime e criam caminhos
# muito longos dentro do ZIP. No Launcher Base 3.x isso pode ultrapassar o
# MAX_PATH clássico do Windows durante Expand-Archive.
QT_BUILD_DIR_PREFIXES = (
    "objects-Debug",
    "objects-RelWithDebInfo",
    "objects-Release",
    "objects-MinSizeRel",
)


@dataclass(slots=True, frozen=True)
class HostBuildManifest:
    schema: str
    engine_version: str
    platform: str
    architecture: str
    executable: str
    executable_sha256: str
    files: int
    bytes: int
    pyinstaller: str
    runtime_manifest: str
    runtime_manifest_sha256: str


def pyinstaller_args(
    *,
    dist_root: Path,
    work_root: Path,
    spec_root: Path,
    console: bool = False,
) -> list[str]:
    args = [
        str(ENTRY),
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        HOST_NAME,
        "--distpath",
        str(dist_root),
        "--workpath",
        str(work_root),
        "--specpath",
        str(spec_root),
        "--paths",
        str(SRC),
        "--collect-all",
        "PySide6",
        "--collect-data",
        "srstudio",
        "--collect-submodules",
        "srstudio.graphics2",
        "--hidden-import",
        "PySide6.QtQuick",
        "--hidden-import",
        "PySide6.QtQml",
        "--hidden-import",
        "PySide6.QtPdf",
        "--noupx",
        "--console" if console else "--windowed",
    ]
    icon = ROOT / "staging" / "logo_update" / "source" / "SR_Studio.ico"
    if icon.is_file():
        args.extend(["--icon", str(icon)])
    return args


def prune_non_runtime_qt_build_artifacts(bundle: Path) -> list[str]:
    """Remove resíduos de compilação do Qt que nunca são usados pelo host.

    PySide6 publica alguns diretórios ``objects-*`` dentro da árvore QML.
    Além de desperdiçarem dezenas de MB, seus nomes podem fazer a extração do
    bundle exceder 260 caracteres no caminho real do usuário. A limpeza é feita
    antes do manifesto de integridade, portanto o catálogo final continua
    descrevendo exatamente o runtime entregue.
    """

    removed: list[str] = []
    directories = sorted(
        (item for item in bundle.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in directories:
        if not any(directory.name.startswith(prefix) for prefix in QT_BUILD_DIR_PREFIXES):
            continue
        try:
            relative = directory.relative_to(bundle).as_posix()
        except ValueError:
            relative = str(directory)
        shutil.rmtree(directory, ignore_errors=False)
        removed.append(relative)
    return sorted(removed)


def max_relative_path_length(bundle: Path) -> tuple[int, str]:
    longest = ""
    for item in bundle.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(bundle).as_posix()
        if len(relative) > len(longest):
            longest = relative
    return len(longest), longest


def build(
    output: str | Path = DEFAULT_DIST,
    *,
    clean: bool = True,
    console: bool = False,
) -> HostBuildManifest:
    if os.name != "nt":
        raise RuntimeError("O host de distribuição Windows deve ser compilado no Windows.")
    if not ENTRY.is_file():
        raise FileNotFoundError(ENTRY)

    try:
        import PyInstaller
        import PyInstaller.__main__
    except Exception as exc:
        raise RuntimeError("Instale o extra de build: pip install -e '.[graphics2-build]'.") from exc

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from srstudio.graphics2 import ENGINE_VERSION
    from srstudio.graphics2.host_runtime import write_runtime_manifest

    output_root = Path(output).resolve()
    dist_root = output_root
    work_root = ROOT / ".build" / "graphics2-host" / "work"
    spec_root = ROOT / ".build" / "graphics2-host" / "spec"
    bundle = dist_root / HOST_NAME

    if clean:
        shutil.rmtree(bundle, ignore_errors=True)
        shutil.rmtree(work_root, ignore_errors=True)
        shutil.rmtree(spec_root, ignore_errors=True)
    dist_root.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    spec_root.mkdir(parents=True, exist_ok=True)

    PyInstaller.__main__.run(
        pyinstaller_args(
            dist_root=dist_root,
            work_root=work_root,
            spec_root=spec_root,
            console=console,
        )
    )

    executable = bundle / f"{HOST_NAME}.exe"
    if not executable.is_file():
        raise RuntimeError(f"PyInstaller não gerou o executável esperado: {executable}")

    removed = prune_non_runtime_qt_build_artifacts(bundle)
    max_path_len, max_path = max_relative_path_length(bundle)
    if removed:
        print(f"Qt build artifacts removidos: {len(removed)} diretório(s)")
    print(f"Maior caminho relativo do host: {max_path_len} caracteres · {max_path}")

    # O manifesto de runtime vive dentro do próprio bundle e cataloga todas as
    # DLLs/plugins/QML restantes. O manifesto de build externo referencia esse catálogo.
    runtime_manifest_path = write_runtime_manifest(
        bundle,
        engine_version=ENGINE_VERSION,
        executable=executable.name,
    )
    files = [item for item in bundle.rglob("*") if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    manifest = HostBuildManifest(
        schema="srstudio/graphics2-host-build-2",
        engine_version=ENGINE_VERSION,
        platform=platform.system(),
        architecture=platform.machine(),
        executable=str(executable.relative_to(dist_root)).replace("\\", "/"),
        executable_sha256=_sha256_file(executable),
        files=len(files),
        bytes=total_bytes,
        pyinstaller=str(getattr(PyInstaller, "__version__", "unknown")),
        runtime_manifest=str(runtime_manifest_path.relative_to(dist_root)).replace("\\", "/"),
        runtime_manifest_sha256=_sha256_file(runtime_manifest_path),
    )
    manifest_path = dist_root / "graphics2-host-manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Graphics Engine 2 host: {executable}")
    print(f"Manifest: {manifest_path}")
    print(f"Runtime integrity: {runtime_manifest_path}")
    return manifest


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Empacota o host Qt do SR Graphics Engine 2 para Windows.")
    parser.add_argument("--output", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument("--console", action="store_true", help="Mantém console para diagnóstico do bundle.")
    parser.add_argument("--print-args", action="store_true", help="Mostra os argumentos PyInstaller e não compila.")
    args = parser.parse_args(argv)
    if args.print_args:
        for item in pyinstaller_args(
            dist_root=args.output.resolve(),
            work_root=(ROOT / ".build" / "graphics2-host" / "work"),
            spec_root=(ROOT / ".build" / "graphics2-host" / "spec"),
            console=args.console,
        ):
            print(item)
        return 0
    try:
        build(args.output, clean=not args.no_clean, console=args.console)
    except Exception as exc:
        print(f"Graphics Engine 2 host build: ERRO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
