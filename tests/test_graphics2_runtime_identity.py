from pathlib import Path

from srstudio.graphics2.host_runtime import load_runtime_manifest, write_runtime_manifest


def test_runtime_manifest_keeps_exact_source_commit(tmp_path: Path):
    (tmp_path / "SRGraphicsEngine2Host.exe").write_bytes(b"host")
    commit = "a" * 40
    write_runtime_manifest(tmp_path, engine_version="2.0-test", source_commit=commit)
    assert load_runtime_manifest(tmp_path).source_commit == commit


def test_launcher_reinstalls_when_component_manifest_hash_changes():
    source = (Path(__file__).resolve().parents[1] / "launcher" / "files" /
              "SRGraphics2Component.ps1").read_text(encoding="utf-8-sig")
    assert "$current.runtime_manifest_sha256 -ne $expectedRuntimeHash" in source
    assert "$sourceReport.runtime_manifest_sha256 -ne $expectedRuntimeHash" in source
