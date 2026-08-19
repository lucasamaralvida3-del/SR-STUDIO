from __future__ import annotations

from pathlib import Path
import sys

import srstudio
import srstudio.graphics2.studio_bridge as studio_bridge_module
from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.graphics2.package import load_package
from srstudio.graphics2.studio_bridge import (
    bridge_flags,
    launch_studio_project_if_enabled,
    prepare_studio_project,
)
from srstudio.settings.features import FeatureFlagStore


def _project() -> StudioProject:
    product = Product(display_name="ACÉM KG", price="25,77", unit="KG", image_path="C:/BancoSR/acem.png")
    card = ProductCard(product_id=product.id, x=120, y=180, width=280, height=230)
    return StudioProject(name="Quinta Filé", products=[product], pages=[Page(name="Página 1", cards=[card])])


def _set_flags(root: Path, *, engine: bool, gpu: bool) -> None:
    store = FeatureFlagStore(root / "feature-flags.json")
    flags = store.load()
    flags.set("graphics_engine_2", engine)
    flags.set("graphics_engine_2_gpu", gpu)
    store.save(flags)


def test_bridge_is_off_by_default_and_never_spawns_process(tmp_path):
    calls = []

    def fake_process(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("processo não deveria ser iniciado")

    result = launch_studio_project_if_enabled(_project(), tmp_path, process_factory=fake_process)

    assert result.ok
    assert not result.launched
    assert calls == []
    assert bridge_flags(tmp_path) == (False, False)


def test_prepare_studio_project_creates_valid_srscene_snapshot_with_products(tmp_path):
    project = _project()
    prepared = prepare_studio_project(project, tmp_path, graphics_api="software")

    assert prepared.package_path.is_file()
    assert prepared.graphics_api == "software"
    restored = load_package(prepared.package_path, extract_assets_to=tmp_path / "extract")
    assert restored.name == project.name
    assert restored.metadata["legacy_project_id"] == project.id
    assert restored.metadata["products"][0]["display_name"] == "ACÉM KG"
    assert restored.active_page.slots


def test_development_bridge_fallback_uses_hardened_entrypoint(monkeypatch):
    monkeypatch.setattr(studio_bridge_module, "discover_packaged_host", lambda: None)
    monkeypatch.delattr(sys, "frozen", raising=False)

    command = studio_bridge_module._host_command()

    assert command == [sys.executable, "-m", "srstudio.graphics2.entrypoint"]
    assert studio_bridge_module._uses_current_python(command)
    assert not studio_bridge_module._uses_current_python(
        [sys.executable, "-m", "srstudio.graphics2.qt_host"]
    )


def test_enabled_bridge_launches_isolated_host_with_snapshot_and_software_backend(tmp_path, monkeypatch):
    _set_flags(tmp_path, engine=True, gpu=False)
    host = tmp_path / "sr-graphics-engine-2-host.exe"
    host.write_bytes(b"MZ-test-host")
    monkeypatch.setenv("SR_GRAPHICS_ENGINE_2_HOST", str(host))
    calls = []

    class Process:
        pid = 4321

    def fake_process(args, **kwargs):
        calls.append((list(args), kwargs))
        return Process()

    result = launch_studio_project_if_enabled(_project(), tmp_path, process_factory=fake_process)

    assert result.ok and result.launched
    assert result.pid == 4321
    assert result.graphics_api == "software"
    assert result.package_path.endswith(".srscene")
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == str(host.resolve())
    assert "--graphics-api" in args
    assert args[args.index("--graphics-api") + 1] == "software"
    assert kwargs["env"]["SR_GRAPHICS_ENGINE_2_BRIDGE"] == "1"
    assert kwargs["env"]["SR_GRAPHICS_ENGINE_2_SOURCE_PROJECT"]


def test_gpu_flag_uses_automatic_accelerated_backend_selection(tmp_path, monkeypatch):
    _set_flags(tmp_path, engine=True, gpu=True)
    host = tmp_path / "graphics2-host.exe"
    host.write_bytes(b"MZ-test-host")
    monkeypatch.setenv("SR_GRAPHICS_ENGINE_2_HOST", str(host))

    class Process:
        pid = 99

    captured = {}

    def fake_process(args, **kwargs):
        captured["args"] = list(args)
        return Process()

    result = launch_studio_project_if_enabled(_project(), tmp_path, process_factory=fake_process)

    assert result.launched
    assert result.graphics_api == "auto"
    assert captured["args"][0] == str(host.resolve())
    assert captured["args"][captured["args"].index("--graphics-api") + 1] == "auto"


def test_turbo_shell_has_one_encartes_destination_g2_only():
    source = (Path(srstudio.__file__).with_name("app") / "turbo_posters.py").read_text(encoding="utf-8")

    # Promoções/Atacado keep their certified productivity modules. Only the
    # Encartes Studio destination is constrained by this mission.
    assert "import srstudio.app.cartazes_productivity as cartazes_productivity" in source
    assert "cartazes_productivity.CartazesProductivityPromotionPosterModule" in source
    assert "cartazes_productivity.CartazesProductivityWholesalePosterModule" in source

    # The official route launches G2 immediately and cannot select another
    # editor through a feature flag, alias, inherited fallback or UI action.
    assert 'if name == "Encartes Studio":' in source
    assert "self._show_graphics2_studio_entrypoint()" in source
    assert "launch_graphics_source" in source
    assert "launch_studio_project(self.project, self.data_dir)" in source
    assert "launch_studio_project_if_enabled" not in source
    assert "bridge_flags(self.data_dir)" not in source
    assert "Abrir editor legado" not in source
    assert '_open_legacy_encartes_fallback' not in source
    assert 'super().navigate("Encartes Studio")' not in source

    # Shared merge/sync infrastructure remains because it is data compatibility,
    # not an alternate product/editor route.
    assert "from srstudio.graphics2.saved_merge import analyze_saved_session_merge, resolve_saved_session_merge" in source
    assert "ask_graphics2_merge_resolutions(self, analysis.report)" in source
    assert "resolve_saved_session_merge(" in source
