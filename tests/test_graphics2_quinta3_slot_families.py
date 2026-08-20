from __future__ import annotations

from collections import Counter
from pathlib import Path

from srstudio.graphics2.item_slots import CUSTOM_PRESETS_KEY, list_item_slot_presets
from srstudio.graphics2.model import GraphicsDocument
from srstudio.graphics2.slot_corpus_families import (
    QUINTA3_FAMILY_PRESETS,
    SINGLETON_FAMILIES,
    SOURCE_SHA256,
    STRICT_TO_BASE_FAMILY,
    family_preset_for_strict_family,
    install_quinta3_family_presets,
    quinta3_family_ids,
    resolve_quinta3_variant,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "g2_slot_corpus" / "ofertas_quinta_file_novo_3_manifest.tsv"
_IMAGE_FIXTURE = Path(__file__).parent / "fixtures" / "g2_slot_corpus" / "ofertas_quinta_file_novo_3_product_images.tsv"


def _rows(path: Path) -> list[dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    header = lines[0].split("\t")
    return [dict(zip(header, line.split("\t"), strict=False)) for line in lines[1:]]


def test_exact_quinta3_manifest_is_frozen_at_expected_source_and_counts() -> None:
    text = _FIXTURE.read_text(encoding="utf-8")
    rows = _rows(_FIXTURE)

    assert "# source=OFERTAS QUINTA FILÉ NOVO (3).pptx" in text
    assert f"# sha256={SOURCE_SHA256}" in text
    assert len(rows) == 28
    assert sum(bool(row["secondary_nodes"]) for row in rows) == 13
    assert sum(bool(row["promotion_nodes"]) for row in rows) == 13
    assert sum(bool(row["club_nodes"]) for row in rows) == 6
    assert {row["primary_unit"] for row in rows} >= {"KG", "UN", "CADA", "QUILO"}

    families = Counter(row["family"] for row in rows)
    assert len(families) == 17
    assert sum(count > 1 for count in families.values()) == 6
    assert sum(count == 1 for count in families.values()) == 11


def test_exact_product_image_provenance_covers_all_products_without_parallel_db() -> None:
    rows = _rows(_IMAGE_FIXTURE)

    assert len(rows) == 28
    assert len({row["product"] for row in rows}) == 28
    assert all(row["normalized"] for row in rows)
    assert all(row["image_nodes"] for row in rows)
    assert all(row["media_parts"].startswith("/ppt/media/") for row in rows)
    assert all(len(row["sha256s"]) == 64 for row in rows)
    assert all(row["source_sha256"] == SOURCE_SHA256 for row in rows)
    assert all(row["page"] == "1" for row in rows)
    assert all(float(row["confidence"]) >= 0.99 for row in rows)

    # Repeated visual copies are one Product↔Image association, not a new family
    # or duplicate Image DB asset.
    repeated = {row["product"] for row in rows if "," in row["image_nodes"]}
    assert repeated == {
        "BEBIDA WHISKY JOHNNIE RED LABEL 1L",
        "ODOR BOOM PERFUME EM CRISTAIS 275G",
        "OLEO ABC PET 900ML SOJA",
        "CADERNOS TURMA DA BELA BROCHURA 80F",
    }


def test_only_recurring_structures_become_reusable_family_presets() -> None:
    assert quinta3_family_ids() == (
        "quinta3-meat-strip",
        "quinta3-wood-plaque",
        "quinta3-compact-promo",
        "quinta3-club-side",
        "quinta3-stationery-round",
    )
    assert len(STRICT_TO_BASE_FAMILY) == 6
    assert len(SINGLETON_FAMILIES) == 11
    assert set(SINGLETON_FAMILIES).isdisjoint(QUINTA3_FAMILY_PRESETS)

    document = GraphicsDocument(name="Quinta 3 learned families")
    installed = install_quinta3_family_presets(document)
    installed_again = install_quinta3_family_presets(document)

    assert installed == installed_again == list(quinta3_family_ids())
    custom = document.metadata[CUSTOM_PRESETS_KEY]
    assert set(custom) == set(quinta3_family_ids())
    listed_ids = {preset["id"] for preset in list_item_slot_presets(document)}
    assert set(quinta3_family_ids()) <= listed_ids
    assert not (SINGLETON_FAMILIES & listed_ids)


def test_unit_wording_never_selects_or_splits_a_family() -> None:
    meat = family_preset_for_strict_family("quinta_meat_strip")
    assert meat is not None
    schema = meat["metadata"]["parameter_schema"]
    assert schema["unit"]["examples"] == ["KG", "UN", "CADA", "QUILO"]
    assert schema["unit"]["family_discriminator"] is False
    assert meat["metadata"]["unit_is_not_family"] is True

    for unit in ("KG", "UN", "CADA", "QUILO"):
        # Family resolution accepts no unit argument by design.
        resolved = resolve_quinta3_variant("quinta_meat_strip")
        assert resolved["preset_id"] == "quinta3-meat-strip", unit


def test_compact_blue_and_beige_are_one_base_slot_with_theme_geometry_variant() -> None:
    blue = resolve_quinta3_variant("quinta_compact_promo_blue", promotion=True)
    beige = resolve_quinta3_variant("quinta_compact_promo_beige", promotion=True)

    assert blue["preset_id"] == beige["preset_id"] == "quinta3-compact-promo"
    assert blue["variant"] == "blue"
    assert beige["variant"] == "beige"
    assert blue["parameters"]["theme"] == "blue"
    assert beige["parameters"]["theme"] == "beige"
    assert "role_overrides" not in blue["parameters"]
    assert beige["parameters"]["role_overrides"]["image"] == [0.0, 0.0, 1.0, 1.0]


def test_wood_plaque_reuses_one_family_for_plain_and_club_promo() -> None:
    plain = resolve_quinta3_variant("quinta_wood_plaque")
    promo = resolve_quinta3_variant("quinta_wood_plaque", promotion=True, club=True)

    assert plain["preset_id"] == promo["preset_id"] == "quinta3-wood-plaque"
    assert plain["variant"] == "plain"
    assert plain["parameters"]["promotionVisible"] is False
    assert promo["variant"] == "club-promo"
    assert promo["parameters"]["promotionVisible"] is True
    assert promo["parameters"]["clubVisible"] is True
    assert promo["parameters"]["secondaryPriceVisible"] is True


def test_image_copies_and_promotion_are_parameters_not_family_discriminators() -> None:
    for preset in QUINTA3_FAMILY_PRESETS.values():
        schema = preset["metadata"]["parameter_schema"]
        for key in ("unit", "promotionVisible", "clubVisible", "secondaryPriceVisible", "imageCopies", "imageScale", "nameLines"):
            assert schema[key]["family_discriminator"] is False

    # Every frozen decoration/media hash must remain a real 64-char SHA.
    hashes = [
        decoration["media_sha256"]
        for preset in QUINTA3_FAMILY_PRESETS.values()
        for decoration in preset["metadata"].get("decorations", [])
        if decoration.get("media_sha256")
    ]
    assert hashes
    assert all(len(item) == 64 for item in hashes)
