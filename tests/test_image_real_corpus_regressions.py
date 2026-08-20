from pathlib import Path

from PIL import Image

from srstudio.images.safe_library import SafeImageLibrary
from srstudio.images.standalone_training import StandaloneImageSource, StandaloneProductImageTrainer


def _image(path: Path) -> Path:
    Image.new("RGB", (320, 480), (235, 235, 235)).save(path)
    return path


def test_rodrigues_pao_de_queijo_filename_vs_sr_catalog_stays_review(tmp_path):
    """Real Library/corpus naming mismatch: Rodrigues packaging vs SR catalog name."""
    source = _image(tmp_path / "pão de queijo sr.png")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(
        library,
        ["PÃO DE QUEIJO CONGELADO SR 1KG"],
    )

    report = trainer.train([StandaloneImageSource(str(source))])

    assert report.accepted == 0
    assert report.review == 1
    assert report.matches[0].product_name == "PÃO DE QUEIJO CONGELADO SR 1KG"
    assert library.find_for_product("PÃO DE QUEIJO CONGELADO SR 1KG")[0].review_status == "pending"


def test_real_145g_hamburger_never_matches_360g_sadia_angus(tmp_path):
    source = _image(tmp_path / "HAMBURGUER CASEIRO 145G.png")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(
        library,
        ["HAMBÚRGUER SADIA ANGUS 360G"],
    )

    report = trainer.train([StandaloneImageSource(str(source))])

    assert report.accepted == 0
    assert report.imported == 0
    assert report.unknown == 1


def test_same_350g_measurement_does_not_override_conflicting_brand(tmp_path):
    source = _image(tmp_path / "FARINHA BEIJU TEMPERADA COM PIMENTA 350G.png")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(
        library,
        ["FARINHA CASEIRINHA TEMP COM PIMENTA 350G"],
    )

    report = trainer.train([StandaloneImageSource(str(source))])

    assert report.accepted == 0
    if report.imported:
        assert report.review == 1
        assert library.find_for_product(report.matches[0].product_name)[0].review_status == "pending"
    else:
        assert report.unknown == 1


def test_opaque_composite_flyer_filename_is_not_product_evidence(tmp_path):
    source = _image(tmp_path / "1000255371.jpg")
    library = SafeImageLibrary(tmp_path / "bank")
    trainer = StandaloneProductImageTrainer(
        library,
        ["MONSTER 473ML", "PÃO DE QUEIJO CONGELADO SR 1KG"],
    )

    report = trainer.train([StandaloneImageSource(str(source))])

    assert report.accepted == 0
    assert report.imported == 0
    assert report.unknown == 1
