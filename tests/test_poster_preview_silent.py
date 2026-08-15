from srstudio.posters.preview import LegacyPosterPreviewService


def test_preview_script_is_patched_to_keep_powerpoint_hidden() -> None:
    source = "$ppt=[Activator]::CreateInstance($t);$ppt.Visible=-1;$pres=$null"
    patched = LegacyPosterPreviewService._silent_script_source(source)
    assert "$ppt.Visible=-1" not in patched
    assert "$ppt.Visible = 0" in patched


def test_preview_script_patch_accepts_spacing_variants() -> None:
    source = "$ppt.Visible = -1\n$ppt.Visible=-1"
    patched = LegacyPosterPreviewService._silent_script_source(source)
    assert "Visible = -1" not in patched
    assert "Visible=-1" not in patched
    assert patched.count("$ppt.Visible = 0") == 2
