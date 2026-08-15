from pathlib import Path

from PIL import Image

from srstudio.app.batch_image_bank_view import BatchImageBankView
from srstudio.images.library import ImageLibrary


def _image(path: Path, value: int) -> Path:
    Image.new("RGB", (120, 160), (value, value, value)).save(path, "PNG")
    return path


def _view_for(library: ImageLibrary) -> BatchImageBankView:
    view = object.__new__(BatchImageBankView)
    view.library = library
    return view


def test_batch_delete_removes_records_and_local_files(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    first = library.import_image(
        _image(tmp_path / "a.png", 30),
        product_name="PRODUTO A",
        kind="product",
        review_status="pending",
    )
    second = library.import_image(
        _image(tmp_path / "b.png", 70),
        product_name="PRODUTO B",
        kind="product",
        review_status="pending",
    )
    first_path = Path(first.path)
    second_path = Path(second.path)
    assert first_path.exists() and second_path.exists()

    view = _view_for(library)
    removed = view._delete_assets([first.id, second.id])

    assert removed == 2
    assert library.all() == []
    assert not first_path.exists()
    assert not second_path.exists()


def test_batch_delete_does_not_unlink_file_outside_bank(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    asset = library.import_image(
        _image(tmp_path / "source.png", 90),
        product_name="PRODUTO",
        kind="product",
        review_status="pending",
    )
    external = _image(tmp_path / "external.png", 120)
    library.update_metadata(asset.id, path=str(external))

    view = _view_for(library)
    removed = view._delete_assets([asset.id])

    assert removed == 1
    assert library.all() == []
    assert external.exists()


def test_batch_approval_preserves_asset_file(tmp_path):
    library = ImageLibrary(tmp_path / "bank")
    asset = library.import_image(
        _image(tmp_path / "approval.png", 150),
        product_name="PRODUTO APROVADO",
        kind="product",
        review_status="pending",
    )
    path = Path(asset.path)

    approved = library.set_review_status(asset.id, "accepted")

    assert approved.review_status == "accepted"
    assert path.exists()
