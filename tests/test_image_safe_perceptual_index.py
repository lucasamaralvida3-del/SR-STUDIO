from pathlib import Path

from PIL import Image, ImageDraw

from srstudio.images.safe_library import SafeImageLibrary


def _pattern(path: Path, seed: int) -> Path:
    image = Image.new("RGB", (320, 480), "white")
    draw = ImageDraw.Draw(image)
    offset = 10 + (seed % 23)
    draw.rectangle((20 + offset, 30, 120 + offset, 420), fill=(30 + seed % 150, 70, 180))
    draw.rectangle((150, 40 + offset, 290, 150 + offset), fill=(220, 30 + seed % 120, 40))
    draw.ellipse((140, 220, 280, 360), fill=(50, 180, 30 + seed % 150))
    image.save(path)
    return path


def test_perceptual_snapshot_is_cached_until_library_changes(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    first_path = _pattern(tmp_path / "first.png", 1)
    library.learn_product_image(first_path, "MONSTER 473ML", confidence=.95)

    first_index, first_payload = library._perceptual_snapshot()
    second_index, second_payload = library._perceptual_snapshot()

    assert first_index is second_index
    assert first_payload is second_payload
    assert first_index.size == 1

    second_path = _pattern(tmp_path / "second.png", 99)
    library.learn_product_image(second_path, "DETERGENTE YPE 500ML", confidence=.95)

    third_index, third_payload = library._perceptual_snapshot()
    assert third_index is not first_index
    assert third_payload is not first_payload
    assert third_index.size == 2


def test_exact_dhash_candidate_query_does_not_return_every_asset(tmp_path):
    library = SafeImageLibrary(tmp_path / "bank")
    assets = []
    for index in range(12):
        path = _pattern(tmp_path / f"product-{index}.png", index * 17 + 3)
        assets.append(
            library.learn_product_image(
                path,
                f"PRODUTO TESTE {index} 500G",
                confidence=.95,
            )
        )

    target = assets[5]
    candidates = library._perceptual_candidates(target.perceptual_hash, 0)

    assert candidates
    assert target.id in {candidate.id for candidate in candidates}
    assert len(candidates) < len(assets)


def test_external_index_change_invalidates_cache_by_file_signature(tmp_path):
    library_a = SafeImageLibrary(tmp_path / "bank")
    library_b = SafeImageLibrary(tmp_path / "bank")
    first = _pattern(tmp_path / "first.png", 7)
    second = _pattern(tmp_path / "second.png", 211)

    library_a.learn_product_image(first, "CAFE VASCONCELOS 500G", confidence=.95)
    cached_index, _ = library_a._perceptual_snapshot()
    assert cached_index.size == 1

    library_b.learn_product_image(second, "MONSTER 473ML", confidence=.95)

    rebuilt_index, _ = library_a._perceptual_snapshot()
    assert rebuilt_index is not cached_index
    assert rebuilt_index.size == 2
