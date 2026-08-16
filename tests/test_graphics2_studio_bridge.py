from __future__ import annotations

from pathlib import Path

import srstudio
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


def test_enabled_bridge_launches_isolated_host_with_snapshot_and_software_backend(tmp_path, monkeypatch):
    _set_flags(tmp_path, engine=True, gpu=False)
    monkeypatch.setenv("SR_GRAPHICS_ENGINE_2_HOST", "sr-graphics-engine-2-host.exe")
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
    assert args[0] == "sr-graphics-engine-2-host.exe"
    assert "--graphics-api" in args
    assert args[args.index("--graphics-api") + 1] == "software"
    assert kwargs["env"]["SR_GRAPHICS_ENGINE_2_BRIDGE"] == "1"
    assert kwargs["env"]["SR_GRAPHICS_ENGINE_2_SOURCE_PROJECT"]


def test_gpu_flag_uses_automatic_accelerated_backend_selection(tmp_path, monkeypatch):
    _set_flags(tmp_path, engine=True, gpu=True)
    monkeypatch.setenv("SR_GRAPHICS_ENGINE_2_HOST", "graphics2-host")

    class Process:
        pid = 99

    captured = {}

    def fake_process(args, **kwargs):
        captured["args"] = list(args)
        return Process()

    result = launch_studio_project_if_enabled(_project(), tmp_path, process_factory=fake_process)

    assert result.launched
    assert result.graphics_api == "auto"
    assert captured["args"][captured["args"].index("--graphics-api") + 1] == "auto"


def test_turbo_shell_exposes_engine2_only_through_feature_flagged_launcher():
    source = (Path(srstudio.__file__).with_name("app") / "turbo_posters.py").read_text(encoding="utf-8")

    assert 'if name == "Encartes Studio":' in source
    assert "self._attach_graphics2_launcher()" in source
    assert "engine_enabled, gpu_enabled = bridge_flags(self.data_dir)" in source
    assert "if not engine_enabled:" in source
    assert 'label = "ENGINE 2 · GPU" if gpu_enabled else "ENGINE 2 · TESTE"' in source
    assert "launch_studio_project_if_enabled(self.project, self.data_dir)" in source
    assert 'tone = "warning" if result.ok else "danger"' in source
