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
QT_RUNTIME_MODULES = (
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtQml",
    "PySide6.QtQuick",
)
FORBIDDEN_QT_RUNTIME_FILES = (
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineQuick.dll",
    "Qt6WebEngineWidgets.dll",
)
QT_BUILD_ARTIFACT_PREFIXES = (
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
    # Deliberadamente NÃO usamos ``--collect-all PySide6``. Esse modo inclui
    # módulos sem relação com o editor (por exemplo QtWebEngine) e fazia o host
    # ultrapassar 700 MB. Os hooks oficiais do PyInstaller coletam plugins,
    # bibliotecas e QML necessários a partir dos módulos Qt realmente usados.
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
        "--collect-data",
        "srstudio",
        "--collect-submodules",
        "srstudio.graphics2",
    ]
    for module in QT_RUNTIME_MODULES:
        args.extend(["--hidden-import", module])
    args.extend(
        [
            "--noupx",
            "--console" if console else "--windowed",
        ]
    )
    icon = ROOT / "staging" / "logo_update" / "source" / "SR_Studio.ico"
    if icon.is_file():
        args.extend(["--icon", str(icon)])
    return args


def prune_qt_build_artifacts(bundle_dir: str | Path) -> tuple[Path, ...]:
    """Remove artefatos de build do Qt que não pertencem ao runtime distribuível."""

    root = Path(bundle_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    candidates = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_dir() and path.name.startswith(QT_BUILD_ARTIFACT_PREFIXES)
        ),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    removed: list[Path] = []
    for path in candidates:
        if not path.exists():
            continue
        shutil.rmtree(path)
        removed.append(path)
    return tuple(removed)


def reject_unexpected_qt_payload(bundle_dir: str | Path) -> None:
    """Impede que módulos Qt pesados e não usados voltem ao host por acidente."""

    root = Path(bundle_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    forbidden = {name.casefold() for name in FORBIDDEN_QT_RUNTIME_FILES}
    found = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name.casefold() in forbidden
    )
    if found:
        raise RuntimeError(
            "Payload Qt não utilizado entrou no Graphics2Host: " + ", ".join(found)
        )


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

    removed = prune_qt_build_artifacts(bundle)
    if removed:
        print(f"Qt build artifacts removidos: {len(removed)}")
        for path in removed:
            print(f"  - {path.relative_to(bundle)}")
    reject_unexpected_qt_payload(bundle)

    # O manifesto de runtime vive dentro do próprio bundle e cataloga todas as
    # DLLs/plugins/QML. O manifesto de build externo referencia esse catálogo.
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
