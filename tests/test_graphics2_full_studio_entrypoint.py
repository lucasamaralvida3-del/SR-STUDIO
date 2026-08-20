from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import inspect
import subprocess
import sys

from srstudio.app import turbo_posters
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

    source = inspect.getsource(full_studio_bridge.launch_studio_project)
    assert "bridge_flags" not in source
    assert "launch_studio_project_if_enabled" not in source


def test_missing_packaged_host_fails_closed_with_complete_diagnostics(tmp_path, monkeypatch) -> None:
    source = tmp_path / "project.srscene"
    source.write_bytes(b"scene")
    log_path = tmp_path / "g2-launch.log"
    searched = [str(tmp_path / "Graphics2Host" / "SRGraphicsEngine2Host.exe")]

    monkeypatch.setattr(full_studio_bridge, "_host_command", lambda: [])
    monkeypatch.setattr(full_studio_bridge, "_host_search_paths", lambda: searched)
    monkeypatch.setattr(full_studio_bridge, "_launch_log_path", lambda: log_path)

    result = full_studio_bridge._launch_host(
        source,
        graphics_api="auto",
        project_name="E2E",
        source_project_id="",
        process_factory=subprocess.Popen,
        message_prefix="G2 opened",
    )

    assert result.ok is False
    assert result.launched is False
    assert "Não foi possível iniciar o Studio de Encartes G2" in result.message
    assert "Host procurado:" in result.message
    assert searched[0] in result.message
    assert "Host encontrado: NÃO ENCONTRADO" in result.message
    assert "SR Studio source/version:" in result.message
    assert "Launcher/runtime:" in result.message
    assert "Motivo:" in result.message
    assert str(source) in result.message
    assert str(log_path) in result.message
    assert log_path.is_file()


def test_real_child_immediate_exit_fails_closed_with_diagnostic_log(tmp_path, monkeypatch) -> None:
    source = tmp_path / "project.srscene"
    source.write_bytes(b"scene")
    log_path = tmp_path / "g2-launch.log"

    monkeypatch.setattr(
        full_studio_bridge,
        "_host_command",
        lambda: [sys.executable, "-c", "import sys; sys.exit(7)"],
    )
    monkeypatch.setattr(full_studio_bridge, "_uses_current_python", lambda _command: False)
    monkeypatch.setattr(full_studio_bridge, "_launch_log_path", lambda: log_path)

    result = full_studio_bridge._launch_host(
        source,
        graphics_api="auto",
        project_name="E2E",
        source_project_id="",
        process_factory=subprocess.Popen,
        message_prefix="G2 opened",
    )

    assert result.ok is False
    assert result.launched is False
    assert "encerrou durante a inicialização" in result.message
    assert "código 7" in result.message
    assert "Host procurado:" in result.message
    assert "Host encontrado:" in result.message
    assert "Launcher/runtime:" in result.message
    assert str(log_path) in result.message
    assert log_path.is_file()
    log = log_path.read_text(encoding="utf-8")
    assert "launching G2" in log
    assert "código 7" in log


def test_encartes_route_is_intercepted_before_inherited_navigation() -> None:
    source = inspect.getsource(SRStudioTurboPosters.navigate)

    intercept = source.index('if name == "Encartes Studio"')
    inherited = source.index("super().navigate(name)")
    assert intercept < inherited
    assert "_show_graphics2_studio_entrypoint" in source


def test_primary_encartes_entrypoint_launches_g2_immediately(tmp_path, monkeypatch) -> None:
    app = object.__new__(SRStudioTurboPosters)
    app.project = StudioProject(name="E2E G2")
    app.data_dir = tmp_path
    expected = SimpleNamespace(ok=True, launched=True, message="G2 opened", pid=4242)
    captured: dict[str, object] = {}

    def fake_launch(project, data_dir):
        captured["project"] = project
        captured["data_dir"] = data_dir
        return expected

    monkeypatch.setattr(turbo_posters, "launch_studio_project", fake_launch)

    def capture_result(result, **kwargs):
        captured["result"] = result
        captured["retry"] = kwargs.get("retry")

    app._show_graphics2_launch_result = capture_result

    SRStudioTurboPosters._show_graphics2_studio_entrypoint(app)

    assert captured["project"] is app.project
    assert captured["data_dir"] == tmp_path
    assert captured["result"] is expected
    assert callable(captured["retry"])


def test_official_shell_contains_no_legacy_encartes_route_or_action() -> None:
    source = inspect.getsource(SRStudioTurboPosters)

    assert '_open_legacy_encartes_fallback' not in source
    assert 'super().navigate("Encartes Studio")' not in source
    assert "Abrir editor legado" not in source
    assert "fallback editor" not in source.casefold()
    assert "StudioEditorExperience" not in source


def test_primary_entrypoint_contains_no_alternative_editor_navigation() -> None:
    source = inspect.getsource(SRStudioTurboPosters._show_graphics2_studio_entrypoint)

    assert "launch_studio_project" in source
    assert "super().navigate" not in source
    assert "feature" not in source.casefold()


def test_primary_launch_failure_uses_explicit_g2_error_dialog(monkeypatch) -> None:
    app = object.__new__(SRStudioTurboPosters)
    calls: list[tuple] = []
    app.toast = SimpleNamespace(show=lambda *args: calls.append(("toast", *args)))
    app._show_graphics2_launch_error = lambda result, **kwargs: calls.append(
        ("dialog", result, kwargs.get("retry"))
    )
    result = SimpleNamespace(ok=False, launched=False, message="host ausente")
    retry = lambda: None

    SRStudioTurboPosters._show_graphics2_launch_result(app, result, retry=retry)

    assert any(call[0] == "toast" for call in calls)
    dialog_call = next(call for call in calls if call[0] == "dialog")
    assert dialog_call[1] is result
    assert dialog_call[2] is retry


def test_error_dialog_contract_has_retry_and_details_and_no_alternative_editor() -> None:
    source = inspect.getsource(SRStudioTurboPosters._show_graphics2_launch_error)

    assert "Não foi possível iniciar o Studio de Encartes G2" in source
    assert "Tentar novamente" in source
    assert "Ver detalhes" in source
    assert "Studio de Encartes G2 — erro" in source
    assert "super().navigate" not in source
    assert "StudioEditorExperience" not in source
    assert "legado" not in source.casefold()


def test_pptx_import_command_routes_directly_to_graphics2() -> None:
    source = inspect.getsource(SRStudioTurboPosters.import_source)

    assert 'source.suffix.lower() == ".pptx"' in source
    assert "self._launch_graphics2_source(source)" in source
    assert "self.workflow.import_source(path)" in source  # Excel compatibility remains.
