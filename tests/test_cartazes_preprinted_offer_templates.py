from __future__ import annotations

import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

MODELS = Path("src/srstudio/assets/poster_templates/legacy/models")

EXPECTED = {'CARTAZ_VENDA.pptx': {'sha256': 'a1bbe94196e94d2b95001bebdc7c4ad2ef4e933e7a47f44f6e95e4c7496e949d',
                       'required_names': ['SR_VENDA_PRECO', 'SR_VENDA_PRODUTO', 'SR_VENDA_UNIDADE'],
                       'slide_size': (6858000, 9906000),
                       'has_limit': False},
 'SEGUNDA_DA_LIMPEZA_1_PRECO.pptx': {'sha256': '407f085439c0c9fc601cb4a7b08c70b3c262043be6758a2262523fac577b1bba',
                                         'required_names': ['SR_CAMPANHA',
                                                            'SR_PRECO_PROMO',
                                                            'SR_PRODUTO',
                                                            'SR_UNIDADE',
                                                            'SR_VALIDADE'],
                                         'slide_size': (6858000, 9906000),
                                         'has_limit': False},
 'SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx': {'sha256': '30d8d86c2cc803aadb2ac74aa904d919ddbb5b4c08b09fbfac9467c64c681754',
                                                    'required_names': ['SR_CAMPANHA',
                                                                       'SR_LIMITE',
                                                                       'SR_PRECO_PROMO',
                                                                       'SR_PRODUTO',
                                                                       'SR_UNIDADE',
                                                                       'SR_VALIDADE'],
                                                    'slide_size': (6858000, 9906000),
                                                    'has_limit': True},
 'SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx': {'sha256': 'c2b6f0fa42ab1413da1addcd24d74cda9487612cb6d5877bd4e1c8b40229ee96',
                                          'required_names': ['SR_CAMPANHA',
                                                             'SR_PRECO_CLUBE',
                                                             'SR_PRECO_PROMO',
                                                             'SR_PRODUTO',
                                                             'SR_UNIDADE_CLUBE',
                                                             'SR_UNIDADE_PROMO',
                                                             'SR_VALIDADE'],
                                          'slide_size': (5376863, 7169150),
                                          'has_limit': False},
 'SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx': {'sha256': 'efd12c3134101a012c24ec300c6a589486b97ebf8b363b757764a4e806b2c38b',
                                                     'required_names': ['SR_CAMPANHA',
                                                                        'SR_LIMITE',
                                                                        'SR_PRECO_CLUBE',
                                                                        'SR_PRECO_PROMO',
                                                                        'SR_PRODUTO',
                                                                        'SR_UNIDADE_CLUBE',
                                                                        'SR_UNIDADE_PROMO',
                                                                        'SR_VALIDADE'],
                                                     'slide_size': (5376863, 7169150),
                                                     'has_limit': True},
 'CLUBE_EXCLUSIVO.pptx': {'sha256': '3a18f1045c9d45ca04bfd612bc86a77fddf00ad9aecad5451bf15fd2307d9435',
                           'required_names': ['SR_CLUBE_PRECO', 'SR_CLUBE_PRODUTO', 'SR_CLUBE_VALIDADE'],
                           'slide_size': (5400675, 7559675),
                           'has_limit': False},
 'CLUBE_EXCLUSIVO_COM_LIMITE.pptx': {'sha256': 'c7714a50a704e9c781c0559f4abc90a3a12c9187b9542817b4eca0ef4c5cd6fc',
                                      'required_names': ['SR_CLUBE_LIMITE',
                                                         'SR_CLUBE_PRECO',
                                                         'SR_CLUBE_PRODUTO',
                                                         'SR_CLUBE_VALIDADE'],
                                      'slide_size': (5400675, 7559675),
                                      'has_limit': True}}

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def _shape_texts(slide_xml: bytes) -> list[str]:
    root = ET.fromstring(slide_xml)
    texts: list[str] = []
    for sp in root.findall(".//p:sp", NS):
        runs = [node.text or "" for node in sp.findall(".//a:t", NS)]
        text = " ".join(" ".join(runs).split()).strip()
        if text:
            texts.append(text)
    return texts


def _shape_names(slide_xml: bytes) -> set[str]:
    root = ET.fromstring(slide_xml)
    return {
        str(node.attrib.get("name") or "")
        for node in root.findall(".//p:cNvPr", NS)
        if node.attrib.get("name")
    }


def _slide_size(presentation_xml: bytes) -> tuple[int, int]:
    root = ET.fromstring(presentation_xml)
    node = root.find(".//p:sldSz", NS)
    assert node is not None
    return int(node.attrib["cx"]), int(node.attrib["cy"])


def test_preprinted_offer_models_are_frozen_and_engine_ready() -> None:
    assert set(EXPECTED) == {
        "CARTAZ_VENDA.pptx",
        "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx",
        "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx",
        "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx",
        "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx",
        "CLUBE_EXCLUSIVO.pptx",
        "CLUBE_EXCLUSIVO_COM_LIMITE.pptx",
    }

    for filename, spec in EXPECTED.items():
        path = MODELS / filename
        assert path.is_file(), filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == spec["sha256"], filename

        with zipfile.ZipFile(path) as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml")
            presentation_xml = archive.read("ppt/presentation.xml")

        names = _shape_names(slide_xml)
        assert set(spec["required_names"]).issubset(names), (filename, names)
        assert _slide_size(presentation_xml) == tuple(spec["slide_size"])

        # The paper now supplies the big fixed OFERTA headline. Other phrases such as
        # "OFERTA DO CLUBE SR" and "OFERTA VÁLIDA" remain legitimate poster content.
        normalized = [re.sub(r"\s+", " ", value).strip().upper() for value in _shape_texts(slide_xml)]
        assert "OFERTA" not in normalized, filename

        limit_names = {"SR_LIMITE", "SR_CLUBE_LIMITE"} & names
        if spec["has_limit"]:
            assert limit_names, filename
        else:
            assert not limit_names, filename


def test_quantity_feature_remains_in_promotion_generator() -> None:
    source = Path("src/srstudio/app/cartazes_table_visual.py").read_text(encoding="utf-8")
    assert 'PROMOTION_COPY_COLUMN = "copies"' in source
    assert 'POSTER_COPIES_KEY = "poster_copies"' in source
    assert '"Qtd. Cartazes"' in source
    assert "expand_promotion_products" in source
