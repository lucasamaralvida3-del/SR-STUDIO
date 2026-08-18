import random

from srstudio.images.perceptual_index import HammingPerceptualIndex, PerceptualIndexEntry


def test_index_returns_exact_and_near_hashes_in_distance_order():
    index = HammingPerceptualIndex(
        [
            PerceptualIndexEntry("exact", "0000000000000000"),
            PerceptualIndexEntry("one-bit", "0000000000000001"),
            PerceptualIndexEntry("far", "ffffffffffffffff"),
        ]
    )

    result = index.search("0000000000000000", 2)

    assert [(distance, entry.asset_id) for distance, entry in result] == [
        (0, "exact"),
        (1, "one-bit"),
    ]


def test_index_keeps_distinct_assets_with_identical_dhash():
    index = HammingPerceptualIndex()
    assert index.add(PerceptualIndexEntry("a", "1234567890abcdef"))
    assert index.add(PerceptualIndexEntry("b", "1234567890abcdef"))

    result = index.search("1234567890abcdef", 0)

    assert {entry.asset_id for _, entry in result} == {"a", "b"}
    assert index.size == 2


def test_index_rejects_invalid_hashes_without_crashing():
    index = HammingPerceptualIndex()
    assert not index.add(PerceptualIndexEntry("bad", "not-a-hash"))
    assert not index.add(PerceptualIndexEntry("too-wide", "1" * 17))
    assert index.search("not-a-hash", 6) == []
    assert index.size == 0


def test_bk_tree_matches_bruteforce_for_large_metadata_set():
    rng = random.Random(20260818)
    entries = [
        PerceptualIndexEntry(f"asset-{index}", f"{rng.getrandbits(64):016x}")
        for index in range(5000)
    ]
    target = entries[2371]
    index = HammingPerceptualIndex(entries)

    actual = {
        entry.asset_id: distance
        for distance, entry in index.search(target.perceptual_hash, 6)
    }
    target_value = int(target.perceptual_hash, 16)
    expected = {
        entry.asset_id: (target_value ^ int(entry.perceptual_hash, 16)).bit_count()
        for entry in entries
        if (target_value ^ int(entry.perceptual_hash, 16)).bit_count() <= 6
    }

    assert actual == expected
    assert actual[target.asset_id] == 0
