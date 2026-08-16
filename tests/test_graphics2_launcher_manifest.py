from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import srstudio


ROOT = Path(srstudio.__file__).resolve().parents[2]
SCRIPT = ROOT / "build" / "create_launcher_manifest.py"
SPEC = spec_from_file_location("sr_create_launcher_manifest", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_launcher_manifest_covers_bootstrap_launcher_and_graphics2_updater_with_real_hashes():
    payload = MODULE.build_launcher_manifest(published_at="2026-08-16T00:00:00+00:00")
    files = {entry["path"]: entry for entry in payload["files"]}

    assert payload["format"] == "SRSTUDIO_LAUNCHER_MANIFEST_1"
    assert payload["bootstrap_version"] == "4.0.1-hybrid.setup3"
    assert payload["launcher_version"] == "4.0.1-hybrid.base3.4"
    assert set(files) == {"SRStudioLauncher.ps1", "SRStudioBootstrap.ps1", "SRGraphics2Component.ps1"}

    for name, entry in files.items():
        path = ROOT / "launcher" / "files" / name
        assert entry["size"] == path.stat().st_size
        assert entry["sha256"] == sha256(path.read_bytes()).hexdigest()
        assert entry["source"] == f"launcher/files/{name}"


def test_normalized_manifest_ignores_only_publication_timestamp():
    left = MODULE.build_launcher_manifest(published_at="2026-08-16T10:00:00+00:00")
    right = MODULE.build_launcher_manifest(published_at="2026-08-17T10:00:00+00:00")
    assert left != right
    assert MODULE.normalized_payload(left) == MODULE.normalized_payload(right)
