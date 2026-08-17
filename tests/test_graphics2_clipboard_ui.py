from __future__ import annotations

from pathlib import Path

import srstudio.graphics2.qt_host as qt_host


def test_project_actions_exposes_copy_paste_buttons_and_standard_shortcuts():
    source = (Path(qt_host.__file__).with_name("qml") / "ProjectActions.qml").read_text(encoding="utf-8")

    assert "StandardKey.Copy" in source
    assert "StandardKey.Paste" in source
    assert "Ctrl+C" in source
    assert "Ctrl+V" in source
    assert "preservando ProductCard/PriceBlock/SmartSlot" in source
    assert '\"name\":\"copy\"' in source
    assert '\"name\":\"paste\"' in source
