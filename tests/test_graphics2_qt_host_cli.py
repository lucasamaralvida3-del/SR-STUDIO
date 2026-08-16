from __future__ import annotations

from pathlib import Path

import pytest

from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.package import save_package
from srstudio.graphics2.qt_host import (
    GRAPHICS_API_CHOICES,
    _normalize_graphics_api,
    build_parser,
    load_launch_context,
)


def test_host_cli_accepts_real_pptx_and_gpu_backend():
    args = build_parser().parse_args(
        ["OFERTAS QUINTA FILÉ NOVO.pptx", "--graphics-api", "d3d11", "--project-name", "Quinta Filé"]
    )
    assert args.source.name == "OFERTAS QUINTA FILÉ NOVO.pptx"
    assert args.graphics_api == "d3d11"
    assert args.project_name == "Quinta Filé"


def test_graphics_api_aliases_are_normalized_and_invalid_values_are_blocked():
    assert _normalize_graphics_api("default") == "auto"
    assert _normalize_graphics_api("Direct3D11") == "d3d11"
    assert _normalize_graphics_api("GL") == "opengl"
    assert set(GRAPHICS_API_CHOICES) >= {"auto", "d3d11", "d3d12", "vulkan", "opengl", "software"}
    with pytest.raises(ValueError):
        _normalize_graphics_api("cuda")


def test_load_launch_context_without_source_creates_clean_document():
    context = load_launch_context(None, project_name="Teste GPU")
    assert context.document.name == "Teste GPU"
    assert context.source is None
    assert context.gate is not None
    assert context.gate.ready


def test_load_launch_context_opens_srscene_and_extracts_portable_resources(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    document = GraphicsDocument(name="Pacote real")
    package = save_package(document, tmp_path / "real.srscene")

    context = load_launch_context(package)

    assert context.document.name == "Pacote real"
    assert context.source == package.resolve()
    assert context.cache_dir is not None
    assert context.cache_dir.is_dir()
    assert context.gate is not None
    assert context.gate.ready


def test_load_launch_context_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_launch_context(Path(tmp_path / "inexistente.pptx"))
