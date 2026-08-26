from __future__ import annotations

import json
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from srstudio.posters import preprinted_offer
from srstudio.posters.legacy_bridge import LegacyPosterBridge


ASSETS = Path("src/srstudio/assets/poster_templates/legacy")
LAYOUT = ASSETS / "preprinted_offer_layouts.json"
NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}

REFERENCE_SHA256 = {
    "CARTAZ_VENDA.pptx": "a1bbe94196e94d2b95001bebdc7c4ad2ef4e933e7a47f44f6e95e4c7496e949d",
    "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx": "407f085439c0c9fc601cb4a7b08c70b3c262043be6758a2262523fac577b1bba",
    "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx": "30d8d86c2cc803aadb2ac74aa904d919ddbb5b4c08b09fbfac9467c64c681754",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx": "c2b6f0fa42ab1413da1addcd24d74cda9487612cb6d5877bd4e1c8b40229ee96",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx": "efd12c3134101a012c24ec300c6a589486b97ebf8b363b757764a4e806b2c38b",
    "CLUBE_EXCLUSIVO.pptx": "3a18f1045c9d45ca04bfd612bc86a77fddf00ad9aecad5451bf15fd2307d9435",
    "CLUBE_EXCLUSIVO_COM_LIMITE.pptx": "c7714a50a704e9c781c0559f4abc90a3a12c9187b9542817b4eca0ef4c5cd6fc",
}


def _shape_map(slide_xml: bytes) -> dict[str, ET.Element]:
    root = ET.fromstring(slide_xml)
    result: dict[str, ET.Element] = {}
    for element in list(root.findall(".//p:sp", NS)) + list(root.findall(".//p:pic", NS)) + list(
        root.findall(".//p:cxnSp", NS)
    ) + list(root.findall(".//p:graphicFrame", NS)) + list(root.findall(".//p:grpSp", NS)):
        node = element.find(".//p:cNvPr", NS)
        if node is not None and node.attrib.get("name"):
            result[str(node.attrib["name"])] = element
    return result


def _geometry(element: ET.Element) -> tuple[int, int, int, int, float]:
    xfrm = element.find(".//a:xfrm", NS)
    assert xfrm is not None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    assert off is not None and ext is not None
    return (
        int(off.attrib["x"]), int(off.attrib["y"]),
        int(ext.attrib["cx"]), int(ext.attrib["cy"]),
        int(xfrm.attrib.get("rot", "0")) / 60000,
    )


def _standalone_offer_texts(slide_xml: bytes) -> list[str]:
    root = ET.fromstring(slide_xml)
    found: list[str] = []
    for element in root.findall(".//p:sp", NS):
        value = " ".join(" ".join((node.text or "") for node in element.findall(".//a:t", NS)).split()).upper()
        letters = re.sub(r"[^A-ZÁÉÍÓÚÂÊÔÃÕÇ]", "", value)
        if letters == "OFERTA":
            found.append(value)
    return found


def test_layout_contract_covers_exact_seven_final_references() -> None:
    raw = json.loads(LAYOUT.read_text(encoding="utf-8"))
    assert raw["format"] == preprinted_offer.LAYOUT_FORMAT
    assert set(raw["models"]) == set(REFERENCE_SHA256)
    # Hashes document the exact seven user-approved PPTX inputs used to derive geometry.
    assert len(set(REFERENCE_SHA256.values())) == 7


def test_runtime_models_match_ground_truth_geometry_and_remove_only_standalone_offer(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    runtime = preprinted_offer.materialize_preprinted_offer_assets(ASSETS)
    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))["models"]

    for name, spec in layout.items():
        path = runtime / "models" / name
        assert path.is_file(), name
        with zipfile.ZipFile(path) as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml")
            presentation_xml = archive.read("ppt/presentation.xml")
        shape_map = _shape_map(slide_xml)
        for shape_name, expected in spec["shapes"].items():
            if shape_name.startswith("SR_"):
                assert shape_name in shape_map, (name, shape_name)
                actual = _geometry(shape_map[shape_name])
                assert actual[:4] == tuple(expected[:4]), (name, shape_name, actual, expected)
                assert abs(actual[4] - float(expected[4])) < 0.001
        root = ET.fromstring(presentation_xml)
        slide_size = root.find(".//p:sldSz", NS)
        assert slide_size is not None
        assert (int(slide_size.attrib["cx"]), int(slide_size.attrib["cy"])) == tuple(spec["slide"])
        assert _standalone_offer_texts(slide_xml) == []


def test_runtime_engine_uses_reference_font_sizes() -> None:
    source = Path("src/srstudio/assets/poster_templates/legacy/engines/PowerPointEngine.ps1").read_text(
        encoding="utf-8-sig"
    )
    for old in preprinted_offer.ENGINE_REPLACEMENTS:
        assert old in source


def test_blank_campaign_no_longer_reintroduces_offer_headline() -> None:
    source = Path("src/srstudio/posters/legacy_bridge.py").read_text(encoding="utf-8")
    assert 'campaign = campaign_override or product.campaign or ""' in source
    assert 'or "OFERTA!!"' not in source


def test_quantity_feature_remains_present_and_expands_pages() -> None:
    source = Path("src/srstudio/app/cartazes_table_visual.py").read_text(encoding="utf-8")
    assert 'PROMOTION_COPY_COLUMN = "copies"' in source
    assert 'POSTER_COPIES_KEY = "poster_copies"' in source
    assert '"Qtd. Cartazes"' in source
    assert "expand_promotion_products" in source


def test_automatic_model_contract_remains_seven_promotion_variants() -> None:
    mapping = LegacyPosterBridge._forced_promotion_spec
    for filename in REFERENCE_SHA256:
        assert mapping(filename) is not None
