import json

import pytest
from PIL import Image

from srstudio.images.standalone_state import (
    STANDALONE_STATE_VERSION,
    StandaloneStateCorruptionError,
    StandaloneStateStore,
    catalog_fingerprint,
    standalone_source_fingerprint,
)
from srstudio.images.standalone_training import StandaloneImageSource


def test_state_store_fails_closed_on_corrupt_json(tmp_path):
    path = tmp_path / "standalone_state.json"
    path.write_text("{broken", encoding="utf-8")
    store = StandaloneStateStore(path)

    with pytest.raises(StandaloneStateCorruptionError):
        store.load()

    assert path.read_text(encoding="utf-8") == "{broken"


def test_state_store_keeps_backup_before_replacement(tmp_path):
    path = tmp_path / "standalone_state.json"
    store = StandaloneStateStore(path)
    first = {"version": STANDALONE_STATE_VERSION, "records": {"a": {"fingerprint": "1"}}}
    second = {"version": STANDALONE_STATE_VERSION, "records": {"b": {"fingerprint": "2"}}}

    store.save(first)
    store.save(second)

    assert json.loads(path.read_text(encoding="utf-8")) == second
    assert json.loads(store.backup_path.read_text(encoding="utf-8")) == first


def test_source_fingerprint_changes_with_file_mapping_and_catalog(tmp_path):
    image = tmp_path / "product.png"
    Image.new("RGB", (100, 100), "white").save(image)
    source = StandaloneImageSource(str(image), product_name="MONSTER 473ML", verified=False)
    catalog_a = catalog_fingerprint(["MONSTER 473ML"])
    catalog_b = catalog_fingerprint(["MONSTER 473ML", "DETERGENTE YPE 500ML"])

    first = standalone_source_fingerprint(source, catalog_a)
    verified = standalone_source_fingerprint(
        StandaloneImageSource(str(image), product_name="MONSTER 473ML", verified=True),
        catalog_a,
    )
    changed_catalog = standalone_source_fingerprint(source, catalog_b)
    Image.new("RGB", (100, 100), "black").save(image)
    changed_file = standalone_source_fingerprint(source, catalog_a)

    assert len({first, verified, changed_catalog, changed_file}) == 4
