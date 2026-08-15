from __future__ import annotations

from pathlib import Path

from srstudio.posters.catalog import PosterModelCatalog
from srstudio.posters.core import PosterKind
from srstudio.posters.legacy_bridge import legacy_models_root


EXPECTED_MODELS = {
    "ATACADO.pptx",
    "CARTAZ_VENDA.pptx",
    "CLUBE_EXCLUSIVO.pptx",
    "CLUBE_EXCLUSIVO_COM_LIMITE.pptx",
    "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx",
    "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx",
}


def test_catalog_exposes_all_programmed_official_models(tmp_path: Path):
    catalog = PosterModelCatalog(tmp_path / "modelos")
    official = catalog.list(groups={PosterModelCatalog.GROUP_OFFICIAL})
    originals = catalog.list(groups={PosterModelCatalog.GROUP_ORIGINAL})

    assert {entry.filename for entry in official} == EXPECTED_MODELS
    assert {entry.filename for entry in originals} == EXPECTED_MODELS
    assert all(entry.read_only for entry in official)
    assert all(entry.read_only for entry in originals)
    assert len(catalog.list(PosterKind.PROMOTION, groups={PosterModelCatalog.GROUP_OFFICIAL})) == 7
    assert len(catalog.list(PosterKind.WHOLESALE, groups={PosterModelCatalog.GROUP_OFFICIAL})) == 1


def test_seeded_originals_are_byte_for_byte_copies(tmp_path: Path):
    catalog = PosterModelCatalog(tmp_path / "modelos")
    for name in EXPECTED_MODELS:
        assert (catalog.originals_root / name).read_bytes() == (legacy_models_root() / name).read_bytes()


def test_custom_model_survives_reindex_and_replacement_creates_version(tmp_path: Path):
    catalog = PosterModelCatalog(tmp_path / "modelos")
    source = tmp_path / "MEU_MODELO.pptx"
    source.write_bytes((legacy_models_root() / "CARTAZ_VENDA.pptx").read_bytes())

    first = catalog.install_custom(source, PosterKind.PROMOTION)
    assert Path(first.path).is_file()
    catalog.reindex()
    assert any(entry.filename == "MEU_MODELO.pptx" for entry in catalog.list(groups={catalog.GROUP_CUSTOM}))

    source.write_bytes((legacy_models_root() / "CLUBE_EXCLUSIVO.pptx").read_bytes())
    catalog.install_custom(source, PosterKind.PROMOTION)
    versions = catalog.list(groups={catalog.GROUP_VERSION})
    assert len(versions) == 1
    assert Path(versions[0].path).is_file()


def test_catalog_templates_keep_historical_engine_metadata(tmp_path: Path):
    catalog = PosterModelCatalog(tmp_path / "modelos")
    entry = next(
        item
        for item in catalog.list(PosterKind.PROMOTION, groups={catalog.GROUP_OFFICIAL})
        if item.filename == "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx"
    )
    template = catalog.to_template(entry)
    assert template.metadata["legacy_engine"] == "promotion"
    assert template.metadata["legacy_model"] == "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx"
    assert template.metadata["catalog_group"] == "Oficiais"
