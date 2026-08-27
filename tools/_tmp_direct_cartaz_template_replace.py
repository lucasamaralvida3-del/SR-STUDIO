from __future__ import annotations

import base64
import hashlib
import json
import shutil
import tempfile
import zlib
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "src" / "srstudio" / "assets" / "poster_templates" / "legacy" / "models"
PAYLOADS = ROOT / "tools" / "_tmp_cartaz_payloads"
ENTRY = "ppt/slides/slide1.xml"
EXPECTED = {
    "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx": "937ae3cffbb7c923d41e0fec55fb14a779ca80f1937484090d17cfe3bf5ecaed",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx": "d5ef9a8af84e167f7a9db87e9d4488adba41351282a8100b90cbe1d70b160a03",
    "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx": "30a5d157591b6fdd92c54ceb9ee2b02356265390625636bf0b69ad08d1562fbc",
    "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx": "c5194a3c488859d8cd0d75e74a81cf85dba7495c8f3511493e3fc51bf59ed1e6",
    "CLUBE_EXCLUSIVO.pptx": "3cd3806929de7af3dda0d5501ac0a88aa613bccc6fa9be563d9aa089c23e77e5",
    "CLUBE_EXCLUSIVO_COM_LIMITE.pptx": "986857eb83991f7de414d387bd99fa0815134c442b558ceb2a05dec7072c02e4",
    "CARTAZ_VENDA.pptx": "e0e5bf34ee6572b2970364614f90119e031d620938b416e3301acbbf41ddadb6",
}


def payload_path(model_name: str) -> Path:
    return PAYLOADS / (Path(model_name).stem + ".txt")


def replace(model_name: str) -> bool:
    model = MODELS / model_name
    slide = zlib.decompress(base64.b64decode(payload_path(model_name).read_text(encoding="ascii").strip()))
    expected = EXPECTED[model_name]
    if hashlib.sha256(slide).hexdigest() != expected:
        raise RuntimeError(f"payload SHA mismatch: {model_name}")
    with ZipFile(model, "r") as source:
        if hashlib.sha256(source.read(ENTRY)).hexdigest() == expected:
            return False
        infos = source.infolist()
        contents = {info.filename: source.read(info.filename) for info in infos}
    contents[ENTRY] = slide
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx", dir=model.parent) as handle:
        tmp = Path(handle.name)
    try:
        with ZipFile(tmp, "w") as dest:
            for info in infos:
                dest.writestr(info, contents[info.filename])
        with ZipFile(tmp, "r") as check:
            bad = check.testzip()
            if bad is not None:
                raise RuntimeError(f"corrupt PPTX {model_name}: {bad}")
            actual = hashlib.sha256(check.read(ENTRY)).hexdigest()
            if actual != expected:
                raise RuntimeError(f"slide SHA mismatch {model_name}: {actual}")
        shutil.move(str(tmp), str(model))
    finally:
        tmp.unlink(missing_ok=True)
    return True


def main() -> int:
    changed = [name for name in EXPECTED if replace(name)]
    print(json.dumps({"changed": changed, "count": len(changed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
