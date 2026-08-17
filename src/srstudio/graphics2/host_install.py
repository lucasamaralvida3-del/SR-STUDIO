from __future__ import annotations

"""Instalação segura do bundle onedir do SR Graphics Engine 2.

Este módulo não ativa feature flags. Ele apenas valida, copia e troca o runtime
Qt de forma atômica, mantendo uma cópia `.previous` para rollback. Assim o
launcher/instalador pode distribuir o host experimental sem arriscar corromper
o Studio Tk principal nem deixar uma instalação parcial após falha de disco.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os
import shutil
import uuid

from .host_runtime import RUNTIME_MANIFEST_NAME, RuntimeHostValidation, validate_runtime_host

INSTALL_RECEIPT_NAME = "graphics2-host-install.json"
INSTALL_RECEIPT_SCHEMA = "srstudio/graphics2-host-install-1"
DEFAULT_INSTALL_SUBDIR = Path("SRStudio") / "App" / "Graphics2Host"


@dataclass(slots=True, frozen=True)
class HostInstallReceipt:
    schema: str
    engine_version: str
    installed_at_utc: str
    executable: str
    executable_sha256: str
    runtime_manifest_sha256: str
    files: int
    source_bundle: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class HostInstallResult:
    ok: bool
    install_dir: Path
    receipt_path: Path | None
    previous_dir: Path | None
    validation: RuntimeHostValidation | None
    message: str


def default_install_dir(local_app_data: str | Path | None = None) -> Path:
    root = str(local_app_data or os.environ.get("LOCALAPPDATA") or "").strip()
    if not root:
        raise RuntimeError("LOCALAPPDATA não está disponível para instalar o host Graphics Engine 2.")
    return Path(root).expanduser().resolve() / DEFAULT_INSTALL_SUBDIR


def install_verified_host(
    source_bundle: str | Path,
    *,
    install_dir: str | Path | None = None,
    expected_engine_version: str | None = None,
    keep_previous: bool = True,
) -> HostInstallResult:
    """Valida o bundle inteiro, copia para staging e troca o runtime atomically."""

    source = Path(source_bundle).expanduser().resolve()
    destination = Path(install_dir).expanduser().resolve() if install_dir is not None else default_install_dir()
    if not source.is_dir():
        return HostInstallResult(False, destination, None, None, None, f"Bundle fonte inexistente: {source}")

    source_validation = validate_runtime_host(
        source,
        full=True,
        expected_engine_version=expected_engine_version,
    )
    if not source_validation.ok:
        detail = source_validation.errors[0] if source_validation.errors else "falha desconhecida"
        return HostInstallResult(False, destination, None, None, source_validation, f"Bundle rejeitado: {detail}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f"{destination.name}.staging-{uuid.uuid4().hex[:10]}")
    previous = destination.with_name(f"{destination.name}.previous")
    shutil.rmtree(staging, ignore_errors=True)

    try:
        shutil.copytree(source, staging)
        copied_validation = validate_runtime_host(
            staging,
            full=True,
            expected_engine_version=expected_engine_version,
        )
        if not copied_validation.ok:
            detail = copied_validation.errors[0] if copied_validation.errors else "falha desconhecida"
            raise RuntimeError(f"Cópia staged falhou na verificação: {detail}")

        receipt = _build_receipt(source, staging, copied_validation)
        receipt_path = staging / INSTALL_RECEIPT_NAME
        _write_json_atomic(receipt_path, receipt.to_dict())

        # O receipt não pertence ao catálogo do runtime gerado pelo build. Ele é
        # metadado de instalação e fica intencionalmente fora da validação full.
        # Por isso a última validação estrita acontece antes de criá-lo.
        if destination.exists():
            shutil.rmtree(previous, ignore_errors=True)
            destination.replace(previous)

        try:
            staging.replace(destination)
        except Exception:
            if previous.exists() and not destination.exists():
                previous.replace(destination)
            raise

        if previous.exists() and not keep_previous:
            shutil.rmtree(previous, ignore_errors=True)
            previous_result: Path | None = None
        else:
            previous_result = previous if previous.exists() else None

        installed_receipt = destination / INSTALL_RECEIPT_NAME
        quick_validation = validate_runtime_host(
            destination,
            full=False,
            expected_engine_version=expected_engine_version,
        )
        if not quick_validation.ok:
            # Esse caminho é extremamente improvável depois da troca atômica,
            # mas ainda fazemos rollback em vez de deixar um host inválido ativo.
            _rollback_after_failed_switch(destination, previous_result)
            detail = quick_validation.errors[0] if quick_validation.errors else "falha desconhecida"
            return HostInstallResult(
                False,
                destination,
                None,
                previous_result,
                quick_validation,
                f"Host instalado falhou na verificação final: {detail}",
            )

        return HostInstallResult(
            True,
            destination,
            installed_receipt,
            previous_result,
            quick_validation,
            f"Host Graphics Engine 2 instalado · versão {copied_validation.engine_version}.",
        )
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        if not destination.exists() and previous.exists():
            previous.replace(destination)
        return HostInstallResult(False, destination, None, previous if previous.exists() else None, source_validation, str(exc))


def rollback_host_install(install_dir: str | Path | None = None) -> HostInstallResult:
    destination = Path(install_dir).expanduser().resolve() if install_dir is not None else default_install_dir()
    previous = destination.with_name(f"{destination.name}.previous")
    if not previous.is_dir():
        return HostInstallResult(False, destination, None, None, None, "Nenhum host anterior disponível para rollback.")

    failed = destination.with_name(f"{destination.name}.failed-{uuid.uuid4().hex[:8]}")
    try:
        if destination.exists():
            destination.replace(failed)
        previous.replace(destination)
        shutil.rmtree(failed, ignore_errors=True)
    except Exception as exc:
        if failed.exists() and not destination.exists():
            failed.replace(destination)
        return HostInstallResult(False, destination, None, previous if previous.exists() else None, None, f"Rollback falhou: {exc}")

    validation = validate_runtime_host(destination, full=False)
    receipt = destination / INSTALL_RECEIPT_NAME
    return HostInstallResult(
        validation.ok,
        destination,
        receipt if receipt.is_file() else None,
        None,
        validation,
        "Rollback do host Graphics Engine 2 concluído." if validation.ok else "Rollback concluído, mas o host anterior falhou na validação.",
    )


def read_install_receipt(install_dir: str | Path | None = None) -> HostInstallReceipt | None:
    destination = Path(install_dir).expanduser().resolve() if install_dir is not None else default_install_dir()
    path = destination / INSTALL_RECEIPT_NAME
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != INSTALL_RECEIPT_SCHEMA:
        return None
    return HostInstallReceipt(
        schema=str(raw.get("schema") or ""),
        engine_version=str(raw.get("engine_version") or ""),
        installed_at_utc=str(raw.get("installed_at_utc") or ""),
        executable=str(raw.get("executable") or ""),
        executable_sha256=str(raw.get("executable_sha256") or ""),
        runtime_manifest_sha256=str(raw.get("runtime_manifest_sha256") or ""),
        files=int(raw.get("files") or 0),
        source_bundle=str(raw.get("source_bundle") or ""),
    )


def _build_receipt(source: Path, staged: Path, validation: RuntimeHostValidation) -> HostInstallReceipt:
    if validation.executable is None:
        raise RuntimeError("Validação não informou executável do host.")
    manifest = staged / RUNTIME_MANIFEST_NAME
    return HostInstallReceipt(
        schema=INSTALL_RECEIPT_SCHEMA,
        engine_version=validation.engine_version,
        installed_at_utc=datetime.now(timezone.utc).isoformat(),
        executable=validation.executable.relative_to(staged).as_posix(),
        executable_sha256=_sha256_file(validation.executable),
        runtime_manifest_sha256=_sha256_file(manifest),
        files=validation.total_files,
        source_bundle=str(source),
    )


def _rollback_after_failed_switch(destination: Path, previous: Path | None) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    if previous is not None and previous.exists():
        previous.replace(destination)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
