from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import base64
import re
import sys

import pytest
import srstudio


ROOT = Path(srstudio.__file__).resolve().parents[2]
INSTALLER = ROOT / "installer" / "SRStudioInstaller.ps1"
BUILDER = ROOT / "installer" / "build_setup.py"
UPDATER = ROOT / "launcher" / "files" / "SRGraphics2Component.ps1"


def test_installer_validates_copies_and_parses_graphics2_updater():
    source = INSTALLER.read_text(encoding="utf-8-sig")

    assert "$InstallerVersion = '4.0.16-setup3'" in source
    assert "__GRAPHICS2_UPDATER_SHA__" in source
    assert "__GRAPHICS2_UPDATER_SIZE__" in source
    assert "Test-PackageFile 'SRGraphics2Component.ps1'" in source
    assert "Copy-Item -LiteralPath $graphics2UpdaterSource" in source
    assert "@('SRStudioBootstrap.ps1','SRStudioLauncher.ps1','SRGraphics2Component.ps1')" in source
    assert "App\\Graphics2Host\\graphics2-host-install.json" in source


def test_setup_builder_embeds_graphics2_updater_and_replaces_integrity_tokens():
    source = BUILDER.read_text(encoding="utf-8")

    assert "graphics2_updater = (ROOT / 'launcher' / 'files' / 'SRGraphics2Component.ps1').read_bytes()" in source
    assert "'__GRAPHICS2_UPDATER_SHA__': sha256(graphics2_updater)" in source
    assert "'__GRAPHICS2_UPDATER_SIZE__': str(len(graphics2_updater))" in source
    assert "X 'GRAPHICS2_UPDATER'" in source
    assert "('GRAPHICS2_UPDATER', graphics2_updater)" in source


def test_setup_builder_generates_self_extracting_payload_with_exact_updater_when_assets_exist(tmp_path):
    icon = ROOT / "staging" / "logo_update" / "source" / "SR_Studio.ico"
    if not icon.is_file():
        pytest.skip("Ícone de staging não disponível neste checkout")

    spec = spec_from_file_location("sr_installer_build_setup", BUILDER)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    output = tmp_path / "SR_STUDIO_SETUP_TESTE.bat"
    module.build("beta", output)
    raw = output.read_text(encoding="utf-8")
    assert "::BEGIN_GRAPHICS2_UPDATER" in raw
    assert "__GRAPHICS2_UPDATER_SHA__" not in raw
    assert "__GRAPHICS2_UPDATER_SIZE__" not in raw

    match = re.search(r"(?s)::BEGIN_GRAPHICS2_UPDATER\r?\n(.*?)\r?\n::END_GRAPHICS2_UPDATER", raw)
    assert match is not None
    decoded = base64.b64decode(re.sub(r"\s", "", match.group(1)))
    assert decoded == UPDATER.read_bytes()
