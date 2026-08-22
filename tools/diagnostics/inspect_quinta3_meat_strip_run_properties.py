from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

REQUESTED_SHA = "21dda44fe758a2899b4c15ffa041b2e0f6ff6d33"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A, "p": P}
ROLE_IDS = {
    "costela": {"name": 49, "currency": 45, "integer": 47, "decimal": 48, "unit": 46},
    "pernil": {"name": 38, "currency": 33, "integer": 36, "decimal": 37, "unit": 35},
    "musculo": {"name": 41, "currency": 39, "integer": 26, "decimal": 27, "unit": 40},
    "moela": {"name": 44, "currency": 42, "integer": 31, "decimal": 43, "unit": 34},
}


def sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            d.update(chunk)
    return d.hexdigest()


def git(source_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source_root), *args], text=True).strip()


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def props(element: ET.Element | None) -> dict:
    if element is None:
        return {"xml": None, "attributes": {}, "latin": None}
    latin = element.find("./a:latin", NS)
    return {
        "xml": ET.tostring(element, encoding="unicode"),
        "attributes": dict(element.attrib),
        "latin": None if latin is None else dict(latin.attrib),
        "children": [local(child.tag) for child in list(element)],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pptx", required=True, type=Path)
    ap.add_argument("--source-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    pptx = args.pptx.resolve()
    source_root = args.source_root.resolve()
    if sha256(pptx) != PPTX_SHA256:
        raise RuntimeError("PPTX SHA mismatch")
    checked = git(source_root, "rev-parse", "HEAD")
    if checked != REQUESTED_SHA:
        raise RuntimeError(f"Exact SHA mismatch: {checked}")

    with zipfile.ZipFile(pptx) as z:
        slide = ET.fromstring(z.read("ppt/slides/slide1.xml"))
    by_id = {}
    for shape in slide.findall(".//p:sp", NS):
        c = shape.find("./p:nvSpPr/p:cNvPr", NS)
        if c is not None:
            by_id[str(c.get("id") or "")] = shape

    nodes = {}
    for profile, roles in ROLE_IDS.items():
        nodes[profile] = {}
        for role, shape_id in roles.items():
            shape = by_id[str(shape_id)]
            paras = []
            for pi, paragraph in enumerate(shape.findall("./p:txBody/a:p", NS)):
                ppr = paragraph.find("./a:pPr", NS)
                defr = None if ppr is None else ppr.find("./a:defRPr", NS)
                runs = []
                for ri, run in enumerate(paragraph.findall("./a:r", NS)):
                    t = run.find("./a:t", NS)
                    rpr = run.find("./a:rPr", NS)
                    runs.append({
                        "index": ri,
                        "text": "" if t is None else (t.text or ""),
                        "rPr": props(rpr),
                    })
                paras.append({
                    "index": pi,
                    "pPr": props(ppr),
                    "defRPr": props(defr),
                    "endParaRPr": props(paragraph.find("./a:endParaRPr", NS)),
                    "runs": runs,
                })
            nodes[profile][role] = {"shape_id": shape_id, "paragraphs": paras}

    renderer = (source_root / "src/srstudio/graphics2/qt_renderer.py").read_text(encoding="utf-8")
    full_card = (source_root / "src/srstudio/graphics2/slot_corpus_full_card.py").read_text(encoding="utf-8")
    payload = {
        "SOURCE_SHA": REQUESTED_SHA,
        "PPTX_SHA256": PPTX_SHA256,
        "RUNTIME_RENDERER_CALLS_SET_KERNING": "setKerning(" in renderer,
        "MEAT_CONTRACT_STORES_KERNING": "kerning" in full_card.casefold() or "kern" in full_card.casefold(),
        "NODES": nodes,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RUNTIME_RENDERER_CALLS_SET_KERNING={payload['RUNTIME_RENDERER_CALLS_SET_KERNING']}")
    print(f"MEAT_CONTRACT_STORES_KERNING={payload['MEAT_CONTRACT_STORES_KERNING']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
