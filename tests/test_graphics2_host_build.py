from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import srstudio
from srstudio.graphics2 import ENGINE_VERSION
from srstudio.graphics2.host_runtime import write_runtime_manifest
from srstudio.graphics2.studio_bridge import HOST_EXE_NAME, discover_packaged_host


ROOT = Path(srstudio.__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "build" / "build_graphics2_host.py"


def _build_module():
    spec = spec_from_file_location("srstudio_graphics2_host_build", BUILD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pyinstaller_contract_is_onedir_windowed_no_upx_and_collects_only_required_qt(tmp_path):
    module = _build_module()
    args = module.pyinstaller_args(
        dist_root=tmp_path / "dist",
        work_root=tmp_path / "work",
        spec_root=tmp_path / "spec",
        console=False,
    )

    assert "--onedir" in args
    assert "--windowed" in args
    assert "--noupx" in args
    assert "--collect-all" not in args
    assert "--collect-data" in args
    assert args[args.index("--collect-data") + 1] == "srstudio"
    assert "--collect-submodules" in args
    assert args[args.index("--collect-submodules") + 1] == "srstudio.graphics2"
    for qt_module in module.QT_RUNTIME_MODULES:
        assert qt_module in args
    assert "PySide6.QtWebEngineCore" not in args
    assert "PySide6.QtPdf" not in args
    assert module.HOST_NAME == "SRGraphicsEngine2Host"


def test_prune_qt_build_artifacts_removes_only_objects_directories(tmp_path):
    module = _build_module()
    bundle = tmp_path / module.HOST_NAME
    keep = bundle / "_internal" / "PySide6" / "Qt" / "qml" / "QtQuick"
    keep.mkdir(parents=True)
    (keep / "qmldir").write_text("module QtQuick", encoding="utf-8")

    release_objects = bundle / "_internal" / "PySide6" / "objects-Release-x86_64"
    nested_objects = bundle / "_internal" / "PySide6" / "Qt" / "objects-RelWithDebInfo-cache"
    release_objects.mkdir(parents=True)
    nested_objects.mkdir(parents=True)
    (release_objects / "temporary.obj").write_bytes(b"build-only")
    (nested_objects / "temporary.obj").write_bytes(b"build-only")

    removed = module.prune_qt_build_artifacts(bundle)

    assert len(removed) == 2
    assert not release_objects.exists()
    assert not nested_objects.exists()
    assert keep.is_dir()
    assert (keep / "qmldir").read_text(encoding="utf-8") == "module QtQuick"


def test_build_entry_uses_hardened_graphics2_entrypoint():
    source = (ROOT / "build" / "graphics2_host_entry.py").read_text(encoding="utf-8")
    assert "from srstudio.graphics2.entrypoint import main" in source
    assert "raise SystemExit(main())" in source


def test_pyproject_has_dedicated_graphics2_build_extra_and_release_entrypoints():
    source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'graphics2-build = ["PySide6>=6.8,<7", "PyInstaller>=6.21,<7"]' in source
    assert 'sr-graphics-engine-2 = "srstudio.graphics2.entrypoint:main"' in source
    assert 'sr-graphics2-release-smoke = "srstudio.graphics2.release_smoke:main"' in source


def test_bridge_discovers_explicit_packaged_host(tmp_path, monkeypatch):
    host = tmp_path / HOST_EXE_NAME
    host.write_bytes(b"MZ-test-host")
    monkeypatch.setenv("SR_GRAPHICS_ENGINE_2_HOST", str(host))

    discovered = discover_packaged_host()

    assert discovered == host.resolve()


def _canonical_bundle(tmp_path: Path, monkeypatch, *, version: str = ENGINE_VERSION) -> tuple[Path, Path]:
    monkeypatch.delenv("SR_GRAPHICS_ENGINE_2_HOST", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    bundle = tmp_path / "SRStudio" / "App" / "Graphics2Host"
    bundle.mkdir(parents=True)
    host = bundle / HOST_EXE_NAME
    host.write_bytes(b"MZ-canonical-host")
    (bundle / "_internal").mkdir()
    (bundle / "_internal" / "Qt6Core.dll").write_bytes(b"qt-core")
    write_runtime_manifest(bundle, engine_version=version)
    return bundle, host


def test_bridge_accepts_canonical_host_only_with_valid_runtime_manifest(tmp_path, monkeypatch):
    _, host = _canonical_bundle(tmp_path, monkeypatch)

    assert discover_packaged_host() == host.resolve()


def test_bridge_rejects_corrupted_canonical_host(tmp_path, monkeypatch):
    _, host = _canonical_bundle(tmp_path, monkeypatch)
    host.write_bytes(b"MZ-corrupted-after-manifest")

    assert discover_packaged_host() is None


def test_bridge_rejects_canonical_host_from_other_engine_version(tmp_path, monkeypatch):
    _canonical_bundle(tmp_path, monkeypatch, version="2.0.0-alpha.other")

    assert discover_packaged_host() is None
