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

    files = [item for item in bundle.rglob("*") if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    manifest = HostBuildManifest(
        schema="srstudio/graphics2-host-build-1",
        engine_version=ENGINE_VERSION,
        platform=platform.system(),
        architecture=platform.machine(),
        executable=str(executable.relative_to(dist_root)).replace("\\", "/"),
        executable_sha256=_sha256_file(executable),
        files=len(files),
        bytes=total_bytes,
        pyinstaller=str(getattr(PyInstaller, "__version__", "unknown")),
    )
    manifest_path = dist_root / "graphics2-host-manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Graphics Engine 2 host: {executable}")
    print(f"Manifest: {manifest_path}")
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
