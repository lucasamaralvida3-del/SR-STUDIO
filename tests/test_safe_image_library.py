import json
from pathlib import Path

import pytest

from srstudio.images.safe_library import ImageLibraryCorruptionError, SafeImageLibrary


def test_corrupt_index_is_not_treated_as_empty_bank(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    library.index_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ImageLibraryCorruptionError):
        library.all()

    assert library.index_path.read_text(encoding="utf-8") == "{broken"


def test_save_keeps_valid_rollback_backup(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    library._save({"first": {"value": 1}})
    original = library.index_path.read_text(encoding="utf-8")

    library._save({"second": {"value": 2}})

    assert library.backup_path.exists()
    assert library.backup_path.read_text(encoding="utf-8") == original
    assert json.loads(library.index_path.read_text(encoding="utf-8")) == {"second": {"value": 2}}


def test_corrupt_existing_index_refuses_overwrite(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    library.index_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(ImageLibraryCorruptionError):
        library._save({})

    assert library.index_path.read_text(encoding="utf-8") == "not-json"
    assert not library.backup_path.exists()
