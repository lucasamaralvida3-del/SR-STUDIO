from pathlib import Path

from srstudio.app.brand import brand_assets_available, brand_dir, icon_path, logo_path


def test_official_brand_assets_are_available() -> None:
    assert brand_assets_available()
    assert logo_path().name == "SR_logo.png"
    assert icon_path().name == "SR_Studio.ico"
    assert logo_path().stat().st_size > 1000
    assert icon_path().stat().st_size > 1000


def test_brand_directory_is_inside_srstudio_package() -> None:
    path = brand_dir()
    parts = [item.casefold() for item in path.parts]
    assert "srstudio" in parts
    assert path.name == "brand"
    assert Path(path / "SR_logo.png").exists()


def test_final_editor_experience_imports_headless() -> None:
    from srstudio.app.editor_experience import StudioCanvasExperience, StudioEditorExperience
    from srstudio.app.professional import SRStudioProfessional

    assert StudioCanvasExperience is not None
    assert StudioEditorExperience is not None
    assert SRStudioProfessional is not None
