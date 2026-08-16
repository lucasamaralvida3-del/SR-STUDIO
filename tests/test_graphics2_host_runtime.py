from __future__ import annotations

from pathlib import Path

from srstudio.graphics2.host_runtime import (
    DEFAULT_HOST_EXE,
    INSTALL_RECEIPT_NAME,
    RUNTIME_MANIFEST_NAME,
    RUNTIME_MANIFEST_SCHEMA,
    build_runtime_manifest,
    load_runtime_manifest,
    validate_runtime_host,
    write_runtime_manifest,
)


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "Graphics2Host"
    (root / "_internal" / "PySide6" / "plugins" / "platforms").mkdir(parents=True)
    (root / DEFAULT_HOST_EXE).write_bytes(b"MZ-host-binary")
    (root / "_internal" / "python311.dll").write_bytes(b"python-runtime")
    (root / "_internal" / "PySide6" / "plugins" / "platforms" / "qwindows.dll").write_bytes(b"qt-platform")
    return root


def test_runtime_manifest_catalogs_every_bundle_file_except_deployment_metadata(tmp_path):
    root = _bundle(tmp_path)
    (root / INSTALL_RECEIPT_NAME).write_text("{}", encoding="utf-8")
    manifest = build_runtime_manifest(root, engine_version="2.0.0-alpha.test")

    assert manifest.schema == RUNTIME_MANIFEST_SCHEMA
    assert manifest.executable == DEFAULT_HOST_EXE
    assert manifest.engine_version == "2.0.0-alpha.test"
    paths = {entry.path for entry in manifest.files}
    assert DEFAULT_HOST_EXE in paths
    assert "_internal/python311.dll" in paths
    assert "_internal/PySide6/plugins/platforms/qwindows.dll" in paths
    assert RUNTIME_MANIFEST_NAME not in paths
    assert INSTALL_RECEIPT_NAME not in paths


def test_full_validation_detects_missing_corrupt_and_extra_files(tmp_path):
    root = _bundle(tmp_path)
    write_runtime_manifest(root, engine_version="2.0.0-alpha.test")

    clean = validate_runtime_host(root, full=True, expected_engine_version="2.0.0-alpha.test")
    assert clean.ok
    assert clean.checked_files == clean.total_files

    target = root / "_internal" / "python311.dll"
    target.write_bytes(b"corrupted")
    corrupt = validate_runtime_host(root, full=True, expected_engine_version="2.0.0-alpha.test")
    assert not corrupt.ok
    assert any("python311.dll" in error and ("Tamanho" in error or "SHA-256" in error) for error in corrupt.errors)

    target.write_bytes(b"python-runtime")
    extra = root / "unexpected.dll"
    extra.write_bytes(b"unexpected")
    with_extra = validate_runtime_host(root, full=True, expected_engine_version="2.0.0-alpha.test")
    assert not with_extra.ok
    assert any("fora do catálogo" in error for error in with_extra.errors)


def test_full_validation_accepts_installer_receipt_but_not_other_extras(tmp_path):
    root = _bundle(tmp_path)
    write_runtime_manifest(root, engine_version="2.0.0-alpha.test")
    (root / INSTALL_RECEIPT_NAME).write_text('{"schema":"srstudio/graphics2-host-install-1"}', encoding="utf-8")

    installed = validate_runtime_host(root, full=True, expected_engine_version="2.0.0-alpha.test")
    assert installed.ok
    assert installed.checked_files == installed.total_files

    (root / "receipt-lookalike.json").write_text("{}", encoding="utf-8")
    invalid = validate_runtime_host(root, full=True, expected_engine_version="2.0.0-alpha.test")
    assert not invalid.ok
    assert any("fora do catálogo" in error for error in invalid.errors)


def test_quick_validation_checks_executable_and_engine_version(tmp_path):
    root = _bundle(tmp_path)
    path = write_runtime_manifest(root, engine_version="2.0.0-alpha.19")
    assert path.is_file()
    loaded = load_runtime_manifest(root)
    assert loaded.executable_sha256

    ok = validate_runtime_host(root, full=False, expected_engine_version="2.0.0-alpha.19")
    assert ok.ok
    assert ok.checked_files == 1

    wrong = validate_runtime_host(root, full=False, expected_engine_version="2.0.0-alpha.20")
    assert not wrong.ok
    assert any("diverge" in error for error in wrong.errors)


def test_runtime_manifest_rejects_executable_path_escape(tmp_path):
    root = _bundle(tmp_path)
    write_runtime_manifest(root, engine_version="test")
    manifest_path = root / RUNTIME_MANIFEST_NAME
    text = manifest_path.read_text(encoding="utf-8").replace(
        f'"executable": "{DEFAULT_HOST_EXE}"',
        '"executable": "../outside.exe"',
    )
    manifest_path.write_text(text, encoding="utf-8")

    result = validate_runtime_host(root, full=False)
    assert not result.ok
    assert any("sai da pasta" in error for error in result.errors)
