from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.editing import PosterProductEditor


def test_editor_records_history_for_manual_change() -> None:
    product = Product(original_name="ACEM", unit="KG", price="31,89")
    editor = PosterProductEditor()

    result = editor.apply(product, PosterKind.PROMOTION, "price1", "30,99")

    assert result.changed is True
    history = product.metadata["edit_history"]
    assert len(history) == 1
    assert history[0]["field"] == "price1"
    assert history[0]["before"] == "31,89"
    assert history[0]["after"] == "30,99"


def test_rapid_edits_same_field_are_coalesced() -> None:
    product = Product(original_name="PRODUTO", unit="UN")
    editor = PosterProductEditor()

    editor.apply(product, PosterKind.PROMOTION, "name", "PRODUTO A")
    editor.apply(product, PosterKind.PROMOTION, "name", "PRODUTO AB")
    editor.apply(product, PosterKind.PROMOTION, "name", "PRODUTO ABC")

    history = product.metadata["edit_history"]
    assert len(history) == 1
    assert history[0]["before"] == "PRODUTO"
    assert history[0]["after"] == "PRODUTO ABC"


def test_batch_style_unit_change_is_audited() -> None:
    product = Product(original_name="ALHO A GRANEL", unit="UN")
    editor = PosterProductEditor()

    editor.apply(product, PosterKind.PROMOTION, "unit", "KG")

    history = product.metadata["edit_history"]
    assert history[-1]["field"] == "unit"
    assert history[-1]["before"] == "UN"
    assert history[-1]["after"] == "KG"
