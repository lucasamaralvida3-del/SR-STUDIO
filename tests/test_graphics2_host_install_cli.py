from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import srstudio
from srstudio.graphics2.host_runtime import DEFAULT_HOST_EXE, write_runtime_manifest


ROOT = Path(srstudio.__file__).resolve().parents[2]
SCRIPT = ROOT / "build" / "install_graphics2_host.py"


def _module():
    spec = spec_from_file_location("srstudio_graphics2_host_install_cli", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bundle(root: Path, version: str) -> Path:
    bundle = root / "bundle"
    (bundle / "_internal").mkdir(parents=True)
    (bundle / DEFAULT_HOST_EXE).write_bytes(b"MZ-cli-host")
    (bundle / "_internal" / "Qt6Core.dll").write_bytes(b"qt-core")
    write_runtime_manifest(bundle, engine_version=version)
    return bundle


def test_cli_script_exposes_install_rollback_and_status_contract():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'sub.add_parser("install"' in source
    assert 'sub.add_parser("rollback"' in source
    assert 'sub.add_parser("status"' in source
    assert "expected_engine_version=ENGINE_VERSION" in source
    assert "install_verified_host(" in source
    assert "rollback_host_install(" in source
    assert "read_install_receipt(" in source


def test_cli_status_returns_one_when_host_is_not_installed(tmp_path, capsys):
    module = _module()
    code = module.main(["status", "--dest", str(tmp_path / "missing")])

    assert code == 1
    assert "não instalado" in capsys.readouterr().out
