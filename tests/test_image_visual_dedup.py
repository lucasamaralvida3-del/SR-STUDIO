import hashlib

from PIL import Image, ImageDraw

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


def test_near_duplicate_keeps_canonical_sha_and_merges_provenance(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    png = tmp_path / "product.png"
    jpg = tmp_path / "product.jpg"
    image = Image.new("RGB", (400, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 40, 330, 560), fill=(210, 25, 30))
    draw.rectangle((90, 140, 310, 240), fill=(250, 220, 20))
    draw.rectangle((120, 320, 280, 500), fill=(245, 245, 245))
    image.save(png)
    image.save(jpg, quality=82)
    png_sha = hashlib.sha256(png.read_bytes()).hexdigest()
    jpg_sha = hashlib.sha256(jpg.read_bytes()).hexdigest()

    first = library.learn_product_image(
        png,
        "CAFE VASCONCELOS 500G",
        confidence=.95,
        metadata={"provenance": [{"source_file": "encarte-a.pptx", "source_slide": 1}]},
    )
    second = library.learn_product_image(
        jpg,
        "CAFE VASCONCELOS 500G",
        confidence=.94,
        metadata={
            "sha256": jpg_sha,
            "provenance": [{"source_file": "encarte-b.pptx", "source_slide": 4}],
        },
    )

    assert second.id == first.id
    assert second.metadata["sha256"] == png_sha
    assert second.metadata["sha256_full"] == png_sha
    assert jpg_sha in second.metadata["variant_sha256"]
    assert {row["source_file"] for row in second.metadata["provenance"]} == {
        "encarte-a.pptx",
        "encarte-b.pptx",
    }


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
