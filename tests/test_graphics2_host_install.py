from __future__ import annotations

from pathlib import Path

import srstudio.graphics2.host_install as host_install_module
from srstudio.graphics2.host_install import (
    INSTALL_RECEIPT_SCHEMA,
    install_verified_host,
    read_install_receipt,
    rollback_host_install,
)
from srstudio.graphics2.host_runtime import DEFAULT_HOST_EXE, RuntimeHostValidation, write_runtime_manifest
from srstudio.settings.features import FeatureFlagStore


def _bundle(root: Path, *, version: str, marker: bytes = b"host-v1") -> Path:
    bundle = root / "bundle"
    (bundle / "_internal" / "PySide6" / "plugins" / "platforms").mkdir(parents=True)
    (bundle / DEFAULT_HOST_EXE).write_bytes(b"MZ-" + marker)
    (bundle / "_internal" / "python311.dll").write_bytes(b"python-runtime-" + marker)
    (bundle / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll").write_bytes(b"qt-" + marker)
    write_runtime_manifest(bundle, engine_version=version)
    return bundle


def test_verified_install_copies_runtime_writes_receipt_and_does_not_enable_flags(tmp_path):
    version = "2.0.0-alpha.install"
    source = _bundle(tmp_path / "source", version=version)
    install_dir = tmp_path / "localapp" / "SRStudio" / "App" / "Graphics2Host"
    flags_path = tmp_path / "localapp" / "SRStudio" / "feature-flags.json"
    flags = FeatureFlagStore(flags_path).load()
    assert not flags.enabled("graphics_engine_2")

    result = install_verified_host(source, install_dir=install_dir, expected_engine_version=version)

    assert result.ok
    assert (install_dir / DEFAULT_HOST_EXE).is_file()
    receipt = read_install_receipt(install_dir)
    assert receipt is not None
    assert receipt.schema == INSTALL_RECEIPT_SCHEMA
    assert receipt.engine_version == version
    assert receipt.executable == DEFAULT_HOST_EXE
    assert receipt.files >= 3
    assert not FeatureFlagStore(flags_path).load().enabled("graphics_engine_2")


def test_install_rejects_corrupt_source_before_touching_existing_runtime(tmp_path):
    version = "2.0.0-alpha.install"
    initial = _bundle(tmp_path / "initial", version=version, marker=b"good")
    install_dir = tmp_path / "Graphics2Host"
    first = install_verified_host(initial, install_dir=install_dir, expected_engine_version=version)
    assert first.ok
    original = (install_dir / DEFAULT_HOST_EXE).read_bytes()

    bad = _bundle(tmp_path / "bad", version=version, marker=b"bad")
    (bad / "_internal" / "python311.dll").write_bytes(b"tampered-after-manifest")
    result = install_verified_host(bad, install_dir=install_dir, expected_engine_version=version)

    assert not result.ok
    assert (install_dir / DEFAULT_HOST_EXE).read_bytes() == original


def test_second_install_keeps_previous_and_rollback_restores_it(tmp_path):
    version = "2.0.0-alpha.install"
    install_dir = tmp_path / "Graphics2Host"
    first_source = _bundle(tmp_path / "one", version=version, marker=b"one")
    second_source = _bundle(tmp_path / "two", version=version, marker=b"two")

    first = install_verified_host(first_source, install_dir=install_dir, expected_engine_version=version)
    assert first.ok
    first_bytes = (install_dir / DEFAULT_HOST_EXE).read_bytes()

    second = install_verified_host(second_source, install_dir=install_dir, expected_engine_version=version)
    assert second.ok
    assert second.previous_dir is not None and second.previous_dir.is_dir()
    assert (install_dir / DEFAULT_HOST_EXE).read_bytes() != first_bytes

    rolled = rollback_host_install(install_dir)
    assert rolled.ok
    assert (install_dir / DEFAULT_HOST_EXE).read_bytes() == first_bytes


def test_discard_previous_waits_until_new_host_passes_final_validation(tmp_path, monkeypatch):
    version = "2.0.0-alpha.install"
    install_dir = tmp_path / "Graphics2Host"
    first_source = _bundle(tmp_path / "one", version=version, marker=b"one")
    second_source = _bundle(tmp_path / "two", version=version, marker=b"two")

    first = install_verified_host(first_source, install_dir=install_dir, expected_engine_version=version)
    assert first.ok
    first_bytes = (install_dir / DEFAULT_HOST_EXE).read_bytes()
    original_validate = host_install_module.validate_runtime_host

    def validate_with_forced_final_failure(bundle, *, full=False, expected_engine_version=None):
        path = Path(bundle).resolve()
        if path == install_dir.resolve() and not full:
            return RuntimeHostValidation(
                ok=False,
                manifest_path=path / "graphics2-host-runtime.json",
                bundle_dir=path,
                executable=path / DEFAULT_HOST_EXE,
                engine_version=version,
                checked_files=1,
                total_files=3,
                errors=("falha final forçada",),
            )
        return original_validate(
            bundle,
            full=full,
            expected_engine_version=expected_engine_version,
        )

    monkeypatch.setattr(host_install_module, "validate_runtime_host", validate_with_forced_final_failure)
    result = install_verified_host(
        second_source,
        install_dir=install_dir,
        expected_engine_version=version,
        keep_previous=False,
    )

    assert not result.ok
    assert "falha final forçada" in result.message
    assert install_dir.is_dir()
    assert (install_dir / DEFAULT_HOST_EXE).read_bytes() == first_bytes


def test_wrong_engine_version_is_rejected(tmp_path):
    source = _bundle(tmp_path / "source", version="2.0.0-alpha.old")
    install_dir = tmp_path / "Graphics2Host"

    result = install_verified_host(
        source,
        install_dir=install_dir,
        expected_engine_version="2.0.0-alpha.new",
    )

    assert not result.ok
    assert not install_dir.exists()
    assert result.validation is not None
    assert any("diverge" in error for error in result.validation.errors)
