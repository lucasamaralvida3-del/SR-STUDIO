from pathlib import Path

from srstudio.updater.manifest import UpdateManifest, build_manifest
from srstudio.updater.transaction import UpdateTransaction


def test_update_manifest_verifies_package(tmp_path: Path) -> None:
    package = tmp_path / "pkg.zip"
    package.write_bytes(b"sr-studio-update")
    manifest = build_manifest(package, "5.0.0-test", "development")
    path = manifest.save(tmp_path / "manifest.json")
    loaded = UpdateManifest.load(path)
    assert loaded.verify_package(package) is True
    package.write_bytes(b"changed")
    assert loaded.verify_package(package) is False


def test_update_transaction_activate_and_rollback(tmp_path: Path) -> None:
    root = tmp_path / "install"
    active = root / "app"
    active.mkdir(parents=True)
    (active / "version.txt").write_text("old", encoding="utf-8")
    new_source = tmp_path / "new"
    new_source.mkdir()
    (new_source / "version.txt").write_text("new", encoding="utf-8")
    transaction = UpdateTransaction(root)
    transaction.stage_directory(new_source)
    result = transaction.activate_staging()
    assert result.ok is True
    assert (active / "version.txt").read_text(encoding="utf-8") == "new"
    rollback = transaction.rollback()
    assert rollback.ok is True
    assert (active / "version.txt").read_text(encoding="utf-8") == "old"
