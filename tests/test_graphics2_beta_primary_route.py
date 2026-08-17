from __future__ import annotations

import os

import srstudio.app.turbo_posters as turbo_posters


def test_beta_build_forces_graphics2_primary_even_without_launcher_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(turbo_posters, "__channel__", "beta")
    monkeypatch.delenv("SR_GRAPHICS_ENGINE_2_BETA", raising=False)
    monkeypatch.delenv("SR_GRAPHICS_ENGINE_2_GPU", raising=False)

    enabled, gpu_enabled = turbo_posters.graphics2_runtime_flags(tmp_path)

    assert enabled is True
    assert gpu_enabled is True
    assert os.environ["SR_GRAPHICS_ENGINE_2_BETA"] == "1"
    assert os.environ["SR_GRAPHICS_ENGINE_2_GPU"] == "1"


def test_stable_build_does_not_force_graphics2(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(turbo_posters, "__channel__", "stable")
    monkeypatch.delenv("SR_GRAPHICS_ENGINE_2_BETA", raising=False)
    monkeypatch.delenv("SR_GRAPHICS_ENGINE_2_GPU", raising=False)

    enabled, gpu_enabled = turbo_posters.graphics2_runtime_flags(tmp_path)

    assert enabled is False
    assert gpu_enabled is False
    assert "SR_GRAPHICS_ENGINE_2_BETA" not in os.environ
    assert "SR_GRAPHICS_ENGINE_2_GPU" not in os.environ
