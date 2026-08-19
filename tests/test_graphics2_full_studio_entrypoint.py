from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect

from srstudio.app.turbo_posters import SRStudioTurboPosters
from srstudio.core.models import StudioProject
from srstudio.graphics2 import full_studio_bridge


class _FakeProcess:
    pid = 4242


def test_direct_pptx_launch_passes_original_source_to_g2_host(tmp_path, monkeypatch) -> None:
    source = tmp_path / "canva-real.pptx"
    source.write_bytes(b"PK\x03\x04")
    captured: dict[str, object] = {}

    monkeypatch.setattr(full_studio_bridge, "_host_command", lambda: ["SRGraphicsEngine2Host.exe"])
    monkeypatch.setattr(full_studio_bridge, "_uses_current_python", lambda _command: False)

    def process_factory(args, **kwargs):
        captured["args"] = list(args)
        captured["kwargs"] = kwargs
        return _FakeProcess()

    result = full_studio_bridge.launch_graphics_source(
        source,
        tmp_path / "data",
        process_factory=process_factory,
    )

    assert result.ok is True
    assert result.launched is True
    assert result.pid == 4242
    args = captured["args"]
    assert args[0] == "SRGraphicsEngine2Host.exe"
    assert args[1] == str(source.resolve())
    assert args[2:4] == ["--graphics-api", "auto"]
    assert args[4:6] == ["--project-name", source.stem]
    assert "SR_GRAPHICS_ENGINE_2_BRIDGE" in captured["kwargs"]["env"]


def test_direct_pptx_launch_fails_closed_when_source_is_missing(tmp_path) -> None:
    result = full_studio_bridge.launch_graphics_source(tmp_path / "missing.pptx", tmp_path / "data")

    assert result.ok is False
    assert result.launched is False
    assert "Arquivo não encontrado" in result.message


def test_direct_launch_fails_closed_for_unsupported_source(tmp_path) -> None:
    source = tmp_path / "unsupported.txt"
    source.write_text("not a studio source", encoding="utf-8")

    result = full_studio_bridge.launch_graphics_source(source, tmp_path / "data")

    assert result.ok is False
    assert result.launched is False
    assert "Formato não suportado" in result.message


def test_primary_current_project_launch_does_not_require_feature_flag(tmp_path, monkeypatch) -> None:
    package = tmp_path / "project.srscene"
    package.write_bytes(b"scene")
    prepared = SimpleNamespace(
        package_path=package,
        gate=SimpleNamespace(ready=True, score=100),
        graphics_api="auto",
        reused_session=True,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(full_studio_bridge, "prepare_studio_project", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(full_studio_bridge, "_host_command", lambda: ["SRGraphicsEngine2Host.exe"])
    monkeypatch.setattr(full_studio_bridge, "_uses_current_python", lambda _command: False)

    def process_factory(args, **kwargs):
        captured["args"] = list(args)
        captured["kwargs"] = kwargs
        return _FakeProcess()

    project = StudioProject(name="Campanha integrada")
    result = full_studio_bridge.launch_studio_project(
        project,
        tmp_path / "data",
        process_factory=process_factory,
    )

    assert result.ok is True
    assert result.launched is True
    assert result.reused_session is True
    assert captured["args"][1] == str(package)
    assert "--project-name" in captured["args"]


def test_encartes_route_is_intercepted_before_legacy_parent_navigation() -> None:
    source = inspect.getsource(SRStudioTurboPosters.navigate)

    intercept = source.index('if name == "Encartes Studio"')
    inherited = source.index("super().navigate(name)")
    assert intercept < inherited
    assert "_show_graphics2_studio_entrypoint" in source


def test_pptx_import_command_routes_directly_to_graphics2() -> None:
    source = inspect.getsource(SRStudioTurboPosters.import_source)

    assert 'source.suffix.lower() == ".pptx"' in source
    assert "self._launch_graphics2_source(source)" in source
    assert "self.workflow.import_source(path)" in source  # Excel compatibility remains.


def test_legacy_editor_remains_explicit_fallback() -> None:
    source = inspect.getsource(SRStudioTurboPosters._open_legacy_encartes_fallback)

    assert 'super().navigate("Encartes Studio")' in source
