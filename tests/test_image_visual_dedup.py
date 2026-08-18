import hashlib

from PIL import Image

from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.visual_dedup import (
    is_conservative_visual_duplicate,
    visual_duplicate_signals,
)


def test_dhash_collision_with_incompatible_geometry_is_not_duplicate():
    signals = visual_duplicate_signals(
        "0000000000000000",
        "0000000000000000",
        (119, 119),
        (2160, 933),
    )
    assert signals.hamming_distance == 0
    assert signals.aspect_delta > 0.50
    assert not is_conservative_visual_duplicate(
        "0000000000000000",
        "0000000000000000",
        (119, 119),
        (2160, 933),
    )


def test_resized_same_aspect_candidate_can_still_be_near_duplicate():
    assert is_conservative_visual_duplicate(
        "1234567890abcdef",
        "1234567890abcdee",
        (500, 1000),
        (1000, 2000),
        max_hamming_distance=2,
    )


def test_safe_library_preserves_complete_sha256_without_breaking_legacy_id(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    source = tmp_path / "product.png"
    Image.new("RGB", (320, 480), (20, 80, 160)).save(source)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()

    asset = library.learn_product_image(source, "LEITE TRIANGULO 1L", confidence=.95)

    assert len(asset.id) == 24
    assert asset.metadata["sha256"] == expected
    assert asset.metadata["sha256_full"] == expected


def test_safe_library_does_not_merge_realistic_dhash_collision_shape(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    square = tmp_path / "square.png"
    wide = tmp_path / "wide.png"
    Image.new("RGB", (119, 119), "white").save(square)
    Image.new("RGB", (2160, 933), "white").save(wide)

    first = library.learn_product_image(
        square,
        "CAFE VASCONCELOS 500G",
        confidence=.95,
    )
    second = library.learn_product_image(
        wide,
        "CAFE VASCONCELOS 500G",
        confidence=.95,
    )

    assert first.perceptual_hash == second.perceptual_hash == "0000000000000000"
    assert first.id != second.id
    assert len(library.find_for_product("CAFE VASCONCELOS 500G")) == 2


def test_safe_library_cross_product_collision_does_not_create_false_conflict(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    square = tmp_path / "square.png"
    wide = tmp_path / "wide.png"
    Image.new("RGB", (119, 119), "white").save(square)
    Image.new("RGB", (2160, 933), "white").save(wide)

    first = library.learn_product_image(square, "TODDY 370G", confidence=.95)
    second = library.learn_product_image(wide, "TODDY 750G", confidence=.95)

    assert first.perceptual_hash == second.perceptual_hash
    assert library.find_cross_product_visual_duplicate(wide, "TODDY 750G") is None
    assert library.find_for_product("TODDY 370G")[0].review_status == "accepted"
    assert library.find_for_product("TODDY 750G")[0].review_status == "accepted"
