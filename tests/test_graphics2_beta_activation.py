from __future__ import annotations

from srstudio.settings.features import FeatureFlagStore


def test_graphics2_remains_off_without_beta_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("SR_GRAPHICS_ENGINE_2_BETA", raising=False)
    monkeypatch.delenv("SR_GRAPHICS_ENGINE_2_GPU", raising=False)

    flags = FeatureFlagStore(tmp_path / "feature-flags.json").load()

    assert not flags.enabled("graphics_engine_2")
    assert not flags.enabled("graphics_engine_2_gpu")


def test_beta_environment_overrides_persisted_false_flags(tmp_path, monkeypatch):
    store = FeatureFlagStore(tmp_path / "feature-flags.json")
    flags = store.load()
    flags.set("graphics_engine_2", False)
    flags.set("graphics_engine_2_gpu", False)
    store.save(flags)

    monkeypatch.setenv("SR_GRAPHICS_ENGINE_2_BETA", "1")
    monkeypatch.setenv("SR_GRAPHICS_ENGINE_2_GPU", "1")
    loaded = store.load()

    assert loaded.enabled("graphics_engine_2")
    assert loaded.enabled("graphics_engine_2_gpu")
