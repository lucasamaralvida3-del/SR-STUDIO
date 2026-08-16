from __future__ import annotations

"""Manifesto de integridade do bundle congelado do Graphics Engine 2.

O host Qt é um bundle onedir: além do EXE existem DLLs, plugins de plataforma,
QML, codecs e bibliotecas Python. Validar somente o executável não detecta uma
instalação parcial. Este módulo gera e verifica um catálogo SHA-256 de todos os
arquivos do bundle sem depender de PySide6, portanto também pode ser usado pelo
instalador/launcher antes de habilitar a feature flag.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import sys

RUNTIME_MANIFEST_NAME = "graphics2-host-runtime.json"
RUNTIME_MANIFEST_SCHEMA = "srstudio/graphics2-host-runtime-1"
DEFAULT_HOST_EXE = "SRGraphicsEngine2Host.exe"
INSTALL_RECEIPT_NAME = "graphics2-host-install.json"
_DEPLOYMENT_METADATA_NAMES = {RUNTIME_MANIFEST_NAME, INSTALL_RECEIPT_NAME}


@dataclass(slots=True, frozen=True)
class RuntimeFileEntry:
    path: str
    size: int
    sha256: str


@dataclass(slots=True, frozen=True)
class RuntimeHostManifest:
    schema: str
    engine_version: str
    executable: str
    executable_size: int
    executable_sha256: str
    files: tuple[RuntimeFileEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["files"] = [asdict(item) for item in self.files]
        return payload


@dataclass(slots=True, frozen=True)
class RuntimeHostValidation:
    ok: bool
    manifest_path: Path
    bundle_dir: Path
    executable: Path | None
    engine_version: str
    checked_files: int
    total_files: int
    errors: tuple[str, ...]


def build_runtime_manifest(
    bundle_dir: str | Path,
    *,
    engine_version: str,
    executable: str = DEFAULT_HOST_EXE,
) -> RuntimeHostManifest:
    root = Path(bundle_dir).resolve()
    exe = (root / executable).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    if not exe.is_file() or not _is_within(exe, root):
        raise FileNotFoundError(f"Executável do host ausente: {exe}")

    entries: list[RuntimeFileEntry] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not path.is_file() or path.name in _DEPLOYMENT_METADATA_NAMES:
            continue
        relative = path.relative_to(root).as_posix()
        entries.append(RuntimeFileEntry(relative, path.stat().st_size, _sha256_file(path)))

    exe_relative = exe.relative_to(root).as_posix()
    exe_entry = next((item for item in entries if item.path == exe_relative), None)
    if exe_entry is None:
        raise RuntimeError("Executável não entrou no catálogo de integridade.")
    return RuntimeHostManifest(
        schema=RUNTIME_MANIFEST_SCHEMA,
        engine_version=str(engine_version),
        executable=exe_relative,
        executable_size=exe_entry.size,
        executable_sha256=exe_entry.sha256,
        files=tuple(entries),
    )


def write_runtime_manifest(
    bundle_dir: str | Path,
    *,
    engine_version: str,
    executable: str = DEFAULT_HOST_EXE,
) -> Path:
    root = Path(bundle_dir).resolve()
    manifest = build_runtime_manifest(root, engine_version=engine_version, executable=executable)
    path = root / RUNTIME_MANIFEST_NAME
    _write_json_atomic(path, manifest.to_dict())
    return path


def load_runtime_manifest(bundle_dir: str | Path) -> RuntimeHostManifest:
    root = Path(bundle_dir).resolve()
    path = root / RUNTIME_MANIFEST_NAME
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Manifesto do host deve ser um objeto JSON.")
    files_raw = raw.get("files") or []
    if not isinstance(files_raw, list):
        raise ValueError("Catálogo de arquivos inválido.")
    files = tuple(
        RuntimeFileEntry(
            path=str(item.get("path") or ""),
            size=int(item.get("size") or 0),
            sha256=str(item.get("sha256") or "").lower(),
        )
        for item in files_raw
        if isinstance(item, dict)
    )
    return RuntimeHostManifest(
        schema=str(raw.get("schema") or ""),
        engine_version=str(raw.get("engine_version") or ""),
        executable=str(raw.get("executable") or ""),
        executable_size=int(raw.get("executable_size") or 0),
        executable_sha256=str(raw.get("executable_sha256") or "").lower(),
        files=files,
    )


def validate_runtime_host(
    bundle_dir: str | Path,
    *,
    full: bool = False,
    expected_engine_version: str | None = None,
) -> RuntimeHostValidation:
    root = Path(bundle_dir).resolve()
    manifest_path = root / RUNTIME_MANIFEST_NAME
    errors: list[str] = []
    if not manifest_path.is_file():
        return RuntimeHostValidation(False, manifest_path, root, None, "", 0, 0, ("Manifesto de runtime ausente.",))
    try:
        manifest = load_runtime_manifest(root)
    except Exception as exc:
        return RuntimeHostValidation(False, manifest_path, root, None, "", 0, 0, (f"Manifesto inválido: {exc}",))

    if manifest.schema != RUNTIME_MANIFEST_SCHEMA:
        errors.append(f"Schema inválido: {manifest.schema or 'vazio'}.")
    if expected_engine_version and manifest.engine_version != str(expected_engine_version):
        errors.append(
            f"Versão do host {manifest.engine_version or 'desconhecida'} diverge do Engine {expected_engine_version}."
        )
    if not manifest.executable:
        errors.append("Executável não declarado no manifesto.")
        executable = None
    else:
        executable = (root / manifest.executable).resolve()
        if not _is_within(executable, root):
            errors.append("Caminho do executável sai da pasta do bundle.")
            executable = None

    checked = 0
    if executable is not None:
        checked += 1
        if not executable.is_file():
            errors.append(f"Executável ausente: {manifest.executable}.")
        else:
            stat = executable.stat()
            if stat.st_size != manifest.executable_size:
                errors.append("Tamanho do executável diverge do manifesto.")
            if _sha256_file(executable) != manifest.executable_sha256:
                errors.append("SHA-256 do executável diverge do manifesto.")

    if full:
        seen: set[str] = set()
        for entry in manifest.files:
            if not entry.path or entry.path in seen:
                errors.append(f"Entrada de catálogo inválida/duplicada: {entry.path!r}.")
                continue
            seen.add(entry.path)
            candidate = (root / entry.path).resolve()
            if not _is_within(candidate, root):
                errors.append(f"Arquivo sai da pasta do bundle: {entry.path}.")
                continue
            if executable is not None and candidate == executable:
                continue
            checked += 1
            if not candidate.is_file():
                errors.append(f"Arquivo ausente: {entry.path}.")
                continue
            stat = candidate.stat()
            if stat.st_size != entry.size:
                errors.append(f"Tamanho divergente: {entry.path}.")
                continue
            if _sha256_file(candidate) != entry.sha256:
                errors.append(f"SHA-256 divergente: {entry.path}.")

        # O manifesto de runtime e o receipt de instalação são metadados de
        # deployment, não payload executável. O receipt nasce somente depois
        # que a cópia staged já passou na validação integral; ignorá-lo aqui
        # permite revalidar uma instalação real sem mascarar DLL/QML extra.
        actual = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name not in _DEPLOYMENT_METADATA_NAMES
        }
        catalog = {entry.path for entry in manifest.files if entry.path}
        extras = sorted(actual - catalog)
        if extras:
            errors.append(f"Bundle contém {len(extras)} arquivo(s) fora do catálogo: {extras[0]}.")

    return RuntimeHostValidation(
        ok=not errors,
        manifest_path=manifest_path,
        bundle_dir=root,
        executable=executable,
        engine_version=manifest.engine_version,
        checked_files=checked,
        total_files=len(manifest.files),
        errors=tuple(errors),
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="sr-graphics2-host-runtime", description="Valida integridade do host Qt congelado.")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--engine-version", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_runtime_host(
        args.bundle,
        full=bool(args.full),
        expected_engine_version=(str(args.engine_version) or None),
    )
    if report.ok:
        print(
            f"SR Graphics2 Host: OK · {report.engine_version} · "
            f"{report.checked_files}/{report.total_files} arquivo(s) verificado(s)"
        )
        return 0
    for error in report.errors:
        print(f"ERRO: {error}", file=sys.stderr)
    return 1


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
