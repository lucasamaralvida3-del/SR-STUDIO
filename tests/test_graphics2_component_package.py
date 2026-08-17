from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import sys
import zipfile

import srstudio
from srstudio.graphics2.host_runtime import DEFAULT_HOST_EXE, write_runtime_manifest


ROOT = Path(srstudio.__file__).resolve().parents[2]
MODULE_PATH = ROOT / "build" / "package_graphics2_component.py"
SPEC = spec_from_file_location("sr_package_graphics2_component", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _build_root(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    bundle = root / "SRGraphicsEngine2Host"
    (bundle / "_internal" / "PySide6").mkdir(parents=True)
    (bundle / DEFAULT_HOST_EXE).write_bytes(b"MZ-host")
    (bundle / "_internal" / "python311.dll").write_bytes(b"python")
    (bundle / "_internal" / "PySide6" / "Qt6Core.dll").write_bytes(b"qt")
    version = "2.0.0-alpha.test"
    write_runtime_manifest(bundle, engine_version=version)
    (root / "graphics2-host-manifest.json").write_text(
        json.dumps({"engine_version": version}),
        encoding="utf-8",
    )
    return root


def test_component_package_is_disabled_by_default_and_hashes_exact_zip(tmp_path):
    root = _build_root(tmp_path)
    output = root / "host.zip"
    descriptor = root / "component.json"

    component = MODULE.package_component(root, output_zip=output, descriptor_path=descriptor)

    assert output.is_file()
    assert descriptor.is_file()
    assert component.schema == "srstudio/graphics2-host-component-1"
    assert component.enabled is False
    assert component.required is False
    assert component.engine_version == "2.0.0-alpha.test"
    assert component.member_prefix == "SRGraphicsEngine2Host"
    assert component.sha256 == sha256(output.read_bytes()).hexdigest()
    assert component.size == output.stat().st_size
    saved = json.loads(descriptor.read_text(encoding="utf-8"))
    assert saved["sha256"] == component.sha256

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert f"SRGraphicsEngine2Host/{DEFAULT_HOST_EXE}" in names
    assert "SRGraphicsEngine2Host/graphics2-host-runtime.json" in names


def test_component_package_rejects_corrupt_runtime_before_distribution(tmp_path):
    root = _build_root(tmp_path)
    (root / "SRGraphicsEngine2Host" / "_internal" / "python311.dll").write_bytes(b"corrupt")

    try:
        MODULE.package_component(root)
    except RuntimeError as exc:
        assert "rejeitado antes do ZIP" in str(exc)
    else:
        raise AssertionError("bundle corrompido não pode virar componente de distribuição")


def test_component_descriptor_can_be_prepared_for_future_release_without_activating_stable(tmp_path):
    root = _build_root(tmp_path)
    component = MODULE.package_component(
        root,
        url="https://example.invalid/SRGraphicsEngine2Host.zip",
        enabled=False,
        required=False,
    )
    payload = component.to_dict()
    assert payload["url"].startswith("https://")
    assert payload["enabled"] is False
    assert payload["required"] is False
