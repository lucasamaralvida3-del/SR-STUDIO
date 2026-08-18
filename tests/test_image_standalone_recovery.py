from PIL import Image

from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_cli import run_incremental_standalone
from srstudio.images.standalone_training import StandaloneImageSource


def test_incremental_reprocesses_when_state_asset_was_removed_from_library(tmp_path):
    image = tmp_path / "MONSTER 473ML.png"
    Image.new("RGB", (240, 360), "white").save(image)
    source = StandaloneImageSource(str(image))
    library = SafeImageLibrary(tmp_path / "bank")
    state = tmp_path / "standalone_state.json"

    first, first_skipped, _ = run_incremental_standalone(
        library,
        [source],
        ["MONSTER 473ML"],
        state_path=state,
    )
    assert first.review == 1
    assert first_skipped == 0
    assert len(library.all()) == 1

    # Simulate a valid library restore/prune that removed the canonical asset but
    # left the independent ingestion state intact. The next run must recover it.
    library._save({})
    assert library.all() == []

    second, second_skipped, _ = run_incremental_standalone(
        library,
        [source],
        ["MONSTER 473ML"],
        state_path=state,
    )

    assert second_skipped == 0
    assert second.discovered == 1
    assert second.review == 1
    assert len(library.all()) == 1
