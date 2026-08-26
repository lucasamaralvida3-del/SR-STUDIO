from __future__ import annotations

"""Materialize poster assets calibrated for paper with OFERTA preprinted.

The official PPTX binaries remain immutable in the package. At runtime we create a
versioned cache that applies only the geometry supplied by the user's seven final
PPTX references, removes a standalone OFERTA headline, and adjusts the proven
PowerPoint engine's font sizes where the historical engine overrode the model.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


LAYOUT_FORMAT = "srstudio-preprinted-offer-layout-1"
CACHE_VERSION = "preprinted-offer-v1"
EMU_PER_POINT = 12700

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": P_NS, "a": A_NS}

REQUIRED_ROLES = {
    "CARTAZ_VENDA.pptx": {"SR_VENDA_PRODUTO", "SR_VENDA_UNIDADE", "SR_VENDA_PRECO"},
    "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx": {
        "SR_PRODUTO", "SR_UNIDADE", "SR_PRECO_PROMO", "SR_VALIDADE", "SR_CAMPANHA"
    },
    "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx": {
        "SR_PRODUTO", "SR_UNIDADE", "SR_PRECO_PROMO", "SR_VALIDADE", "SR_CAMPANHA", "SR_LIMITE"
    },
    "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx": {
        "SR_PRODUTO", "SR_UNIDADE_PROMO", "SR_PRECO_PROMO", "SR_UNIDADE_CLUBE",
        "SR_PRECO_CLUBE", "SR_VALIDADE", "SR_CAMPANHA"
    },
    "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx": {
        "SR_PRODUTO", "SR_UNIDADE_PROMO", "SR_PRECO_PROMO", "SR_UNIDADE_CLUBE",
        "SR_PRECO_CLUBE", "SR_VALIDADE", "SR_CAMPANHA", "SR_LIMITE"
    },
    "CLUBE_EXCLUSIVO.pptx": {"SR_CLUBE_PRODUTO", "SR_CLUBE_PRECO", "SR_CLUBE_VALIDADE"},
    "CLUBE_EXCLUSIVO_COM_LIMITE.pptx": {
        "SR_CLUBE_PRODUTO", "SR_CLUBE_PRECO", "SR_CLUBE_VALIDADE", "SR_CLUBE_LIMITE"
    },
}

ENGINE_REPLACEMENTS = {
    'Set-TextExact $unit ([string]$job.unidade_exibicao) 14.0':
        'Set-TextExact $unit ([string]$job.unidade_exibicao) 50.79',
    'Set-TextExact $unit1 ([string]$job.unidade_exibicao) 12.0':
        'Set-TextExact $unit1 ([string]$job.unidade_exibicao) 36.0',
    'Set-TextExact $unit2 ([string]$job.unidade_exibicao) 12.0':
        'Set-TextExact $unit2 ([string]$job.unidade_exibicao) 44.0',
    'Set-ProductFitKeepStyleMaxLines $prod ([string]$job.produto) 66.0 24.0 3':
        'Set-ProductFitKeepStyleMaxLines $prod ([string]$job.produto) 72.0 24.0 3',
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _layout_path(packaged_root: Path) -> Path:
    return packaged_root / "preprinted_offer_layouts.json"


def _load_layout(packaged_root: Path) -> dict[str, object]:
    path = _layout_path(packaged_root)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("format") != LAYOUT_FORMAT or not isinstance(raw.get("models"), dict):
        raise RuntimeError("Contrato de layout dos cartazes OFERTA pré-impresso inválido.")
    return raw


def _cache_signature(packaged_root: Path, layout: dict[str, object]) -> str:
    models_root = packaged_root / "models"
    engines_root = packaged_root / "engines"
    payload = {
        "version": CACHE_VERSION,
        "layout": _sha256_file(_layout_path(packaged_root)),
        "models": {
            name: _sha256_file(models_root / name)
            for name in sorted(REQUIRED_ROLES)
            if (models_root / name).is_file()
        },
        "engine": _sha256_file(engines_root / "PowerPointEngine.ps1"),
    }
    return _sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def _letters_only(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in normalized.upper() if "A" <= ch <= "Z")


def _shape_name(element: ET.Element) -> str:
    node = element.find(".//p:cNvPr", NS)
    return str(node.attrib.get("name") or "") if node is not None else ""


def _shape_text(element: ET.Element) -> str:
    return " ".join(" ".join((node.text or "") for node in element.findall(".//a:t", NS)).split())


def _apply_shape_geometry(element: ET.Element, geometry: list[object]) -> bool:
    xfrm = element.find(".//a:xfrm", NS)
    if xfrm is None:
        return False
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return False
    x, y, width, height, rotation = geometry
    off.set("x", str(int(x)))
    off.set("y", str(int(y)))
    ext.set("cx", str(int(width)))
    ext.set("cy", str(int(height)))
    rot = float(rotation or 0.0)
    if rot:
        xfrm.set("rot", str(int(round(rot * 60000))))
    else:
        xfrm.attrib.pop("rot", None)
    return True


def _rewrite_slide(slide_xml: bytes, spec: dict[str, object], model_name: str) -> bytes:
    root = ET.fromstring(slide_xml)
    geometry_by_name = spec.get("shapes")
    if not isinstance(geometry_by_name, dict):
        raise RuntimeError(f"Layout sem shapes: {model_name}")

    seen: set[str] = set()
    for element in list(root.findall(".//p:sp", NS)) + list(root.findall(".//p:pic", NS)) + list(
        root.findall(".//p:cxnSp", NS)
    ) + list(root.findall(".//p:graphicFrame", NS)) + list(root.findall(".//p:grpSp", NS)):
        name = _shape_name(element)
        geometry = geometry_by_name.get(name)
        if isinstance(geometry, list) and len(geometry) == 5 and _apply_shape_geometry(element, geometry):
            seen.add(name)

        # The physical paper now provides this one large fixed headline. Do not
        # remove legitimate phrases such as OFERTA VÁLIDA or OFERTA DO CLUBE SR.
        if element.tag == f"{{{P_NS}}}sp" and _letters_only(_shape_text(element)) == "OFERTA":
            for text_node in element.findall(".//a:t", NS):
                text_node.text = ""

    missing_roles = REQUIRED_ROLES.get(model_name, set()) - seen
    if missing_roles:
        raise RuntimeError(f"Modelo {model_name} sem roles calibráveis: {', '.join(sorted(missing_roles))}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rewrite_presentation(presentation_xml: bytes, spec: dict[str, object], model_name: str) -> bytes:
    root = ET.fromstring(presentation_xml)
    slide_size = spec.get("slide")
    node = root.find(".//p:sldSz", NS)
    if node is None or not isinstance(slide_size, list) or len(slide_size) != 2:
        raise RuntimeError(f"Tamanho do slide inválido: {model_name}")
    node.set("cx", str(int(slide_size[0])))
    node.set("cy", str(int(slide_size[1])))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rewrite_model(source: Path, destination: Path, spec: dict[str, object]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{source.stem}-", suffix=".pptx", dir=destination.parent, delete=False) as fh:
        temporary = Path(fh.name)
    try:
        with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(temporary, "w") as target:
            for info in original.infolist():
                data = original.read(info.filename)
                if info.filename == "ppt/slides/slide1.xml":
                    data = _rewrite_slide(data, spec, source.name)
                elif info.filename == "ppt/presentation.xml":
                    data = _rewrite_presentation(data, spec, source.name)
                target.writestr(info, data)
        with zipfile.ZipFile(temporary, "r") as check:
            bad = check.testzip()
            if bad:
                raise RuntimeError(f"PPTX runtime corrompido em {bad}: {source.name}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _rewrite_engine(source: Path, destination: Path) -> None:
    text = source.read_text(encoding="utf-8-sig")
    for old, new in ENGINE_REPLACEMENTS.items():
        if old not in text:
            raise RuntimeError(f"Contrato do engine mudou; trecho não encontrado: {old}")
        text = text.replace(old, new, 1)
    destination.write_text(text, encoding="utf-8-sig")


def materialize_preprinted_offer_assets(packaged_root: str | Path) -> Path:
    """Return a cached legacy asset root calibrated to the seven approved layouts."""

    packaged = Path(packaged_root)
    layout = _load_layout(packaged)
    signature = _cache_signature(packaged, layout)
    cache = Path.home() / ".srstudio5" / "runtime-poster-assets" / CACHE_VERSION
    marker = cache / ".signature"
    if marker.is_file() and marker.read_text(encoding="ascii").strip() == signature:
        if (cache / "models").is_dir() and (cache / "engines" / "PowerPointEngine.ps1").is_file():
            return cache

    temporary = cache.with_name(cache.name + ".tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    (temporary / "models").mkdir(parents=True, exist_ok=True)
    (temporary / "engines").mkdir(parents=True, exist_ok=True)

    models = layout["models"]
    for source in sorted((packaged / "models").glob("*.pptx")):
        destination = temporary / "models" / source.name
        spec = models.get(source.name) if isinstance(models, dict) else None
        if isinstance(spec, dict):
            _rewrite_model(source, destination, spec)
        else:
            shutil.copy2(source, destination)

    for source in sorted((packaged / "engines").glob("*.ps1")):
        destination = temporary / "engines" / source.name
        if source.name == "PowerPointEngine.ps1":
            _rewrite_engine(source, destination)
        else:
            shutil.copy2(source, destination)

    (temporary / ".signature").write_text(signature, encoding="ascii")
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(cache, ignore_errors=True)
    os.replace(temporary, cache)
    return cache


__all__ = ["CACHE_VERSION", "ENGINE_REPLACEMENTS", "materialize_preprinted_offer_assets"]
