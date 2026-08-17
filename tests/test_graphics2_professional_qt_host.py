from __future__ import annotations

from pathlib import Path

from srstudio.graphics2 import professional_qt_host
from srstudio.graphics2.command_router import GraphicsCommandRouter
from srstudio.graphics2.professional_command_router import ProfessionalGraphicsCommandRouter


def test_professional_router_context_is_opt_in_and_restores_base_host():
    base = professional_qt_host.base
    original = base.GraphicsCommandRouter
    assert original is GraphicsCommandRouter
    with professional_qt_host.professional_router_enabled():
        assert base.GraphicsCommandRouter is ProfessionalGraphicsCommandRouter
    assert base.GraphicsCommandRouter is original


def test_professional_host_context_attaches_tools_once_and_restores_hooks(monkeypatch):
    base = professional_qt_host.base
    original_router = base.GraphicsCommandRouter
    original_attach = base._attach_context_qml_tool
    calls = []

    def fake_attach(engine, root_window, qml_path, **kwargs):
        calls.append(Path(qml_path).name)
        return object(), object()

    monkeypatch.setattr(base, "_attach_context_qml_tool", fake_attach)
    patched_before = base._attach_context_qml_tool
    with professional_qt_host.professional_host_enabled():
        assert base.GraphicsCommandRouter is ProfessionalGraphicsCommandRouter
        base._attach_context_qml_tool("engine", "root", Path("/tmp/ImageInspector.qml"))
        base._attach_context_qml_tool("engine", "root", Path("/tmp/QualityInspector.qml"))
        base._attach_context_qml_tool("engine", "root", Path("/tmp/ProjectActions.qml"))
        assert calls == [
            "ImageInspector.qml",
            "ProfessionalInspector.qml",
            "ProfessionalRecovery.qml",
            "QualityInspector.qml",
            "ProjectActions.qml",
        ]
    assert base.GraphicsCommandRouter is original_router
    assert base._attach_context_qml_tool is patched_before
    monkeypatch.setattr(base, "_attach_context_qml_tool", original_attach)


def test_professional_launch_uses_professional_router_without_persistent_patch(monkeypatch):
    base = professional_qt_host.base
    original_router = base.GraphicsCommandRouter
    calls = []

    def fake_launch(*args, **kwargs):
        calls.append((base.GraphicsCommandRouter, args, kwargs))
        return 17

    monkeypatch.setattr(base, "launch_qt_quick_editor", fake_launch)
    result = professional_qt_host.launch_qt_quick_editor("doc", graphics_api="software")
    assert result == 17
    assert calls[0][0] is ProfessionalGraphicsCommandRouter
    assert calls[0][1] == ("doc",)
    assert calls[0][2]["graphics_api"] == "software"
    assert base.GraphicsCommandRouter is original_router


def test_professional_main_patches_router_only_during_base_main(monkeypatch):
    base = professional_qt_host.base
    original_router = base.GraphicsCommandRouter
    seen = []

    def fake_main(argv):
        seen.append((base.GraphicsCommandRouter, argv))
        return 23

    monkeypatch.setattr(base, "main", fake_main)
    result = professional_qt_host.main(["--probe-graphics-api"])
    assert result == 23
    assert seen == [(ProfessionalGraphicsCommandRouter, ["--probe-graphics-api"])]
    assert base.GraphicsCommandRouter is original_router
