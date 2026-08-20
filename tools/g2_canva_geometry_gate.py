from __future__ import annotations

"""Hash-locked semantic geometry gate for the real G2 Canva corpus.

This gate intentionally reads PPTX package metadata only.  It never loads or
compares JPEG/PNG references and therefore is independent of visual-fidelity
approval.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import zipfile

from srstudio.graphics2.pptx_native_canvas import resolve_pptx_native_canvas

EXPECTED_SLIDES = {
    "quinta-file-2026-08-13": [12, 13, 14, 15],
    "terca-verde-2026-08-11": [5, 6, 8],
    "quarta-cafe-2026-08-12": [7, 8, 9, 10],
}
EXPECTED_CANVAS = {"width": 1080.0, "height": 1350.0}
EXPECTED_PHYSICAL = {
    "width_emu": 10_287_000,
    "height_emu": 12_852_400,
    "width_pt": 810.0,
    "height_pt": 1012.0,
}
_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


def run_gate(corpus_root: Path, manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = {item["document_id"]: item for item in manifest.get("documents") or []}
    cases = list(manifest.get("cases") or [])
    errors: list[str] = []
    reports: list[dict[str, object]] = []
    passed_pages = 0

    if manifest.get("acceptance_thresholds") is not None:
        errors.append("acceptance_thresholds must remain null for the G2 visual corpus")

    actual_case_map: dict[str, list[int]] = {}
    for case in cases:
        actual_case_map.setdefault(str(case.get("document_id") or ""), []).append(int(case.get("slide_number") or 0))
    actual_case_map = {key: sorted(value) for key, value in actual_case_map.items()}
    if actual_case_map != {key: sorted(value) for key, value in EXPECTED_SLIDES.items()}:
        errors.append(f"manifest slide mapping mismatch: {actual_case_map}")

    for document_id, slide_numbers in EXPECTED_SLIDES.items():
        item = documents.get(document_id)
        if item is None:
            errors.append(f"missing manifest document: {document_id}")
            continue
        source_name = str(item.get("source_pptx") or "")
        source = corpus_root / source_name
        if not source.is_file():
            errors.append(f"missing real PPTX: {source_name}")
            continue

        digest = sha256(source.read_bytes()).hexdigest()
        expected_digest = str(item.get("source_pptx_sha256") or "")
        if digest != expected_digest:
            errors.append(f"SHA-256 mismatch for {source_name}: {digest} != {expected_digest}")
            continue

        resolution = resolve_pptx_native_canvas(source)
        metadata = resolution.to_metadata()
        if resolution.source_kind != "canva" or resolution.source_confidence != "reliable":
            errors.append(f"Canva provenance not reliable for {source_name}: {metadata}")
        if resolution.source_design_id != str(item.get("canva_document_id") or ""):
            errors.append(
                f"Canva design id mismatch for {source_name}: "
                f"{resolution.source_design_id} != {item.get('canva_document_id')}"
            )
        if metadata["pptx_physical_page_size"] != EXPECTED_PHYSICAL:
            errors.append(f"physical page mismatch for {source_name}: {metadata['pptx_physical_page_size']}")
        if metadata["intended_canvas_size"] != EXPECTED_CANVAS:
            errors.append(f"intended canvas mismatch for {source_name}: {metadata['intended_canvas_size']}")
        if not resolution.uses_intended_canvas_size:
            errors.append(f"semantic intended canvas was not activated for {source_name}")

        with zipfile.ZipFile(source) as archive:
            available_slides = {
                int(match.group(1))
                for name in archive.namelist()
                if (match := _SLIDE_RE.fullmatch(name)) is not None
            }
        missing_slides = [number for number in slide_numbers if number not in available_slides]
        if missing_slides:
            errors.append(f"missing requested slides in {source_name}: {missing_slides}")
        else:
            passed_pages += len(slide_numbers)

        reports.append(
            {
                "document_id": document_id,
                "source_pptx": source_name,
                "sha256": digest,
                "design_id": resolution.source_design_id,
                "slides": slide_numbers,
                "pptx_physical_page_size": metadata["pptx_physical_page_size"],
                "intended_canvas_size": metadata["intended_canvas_size"],
                "preset": metadata["preset"],
                "source": metadata["source"],
                "source_profile": metadata["source_profile"],
                "origin_evidence": metadata["origin_evidence"],
            }
        )

    result = {
        "schema": "srstudio/g2-canva-real-geometry-gate/1",
        "status": "pass" if not errors and passed_pages == 11 else "fail",
        "real_canva_geometry": f"{passed_pages}/11",
        "official_lossless_png": "0/11",
        "visual_gate": "WAITING_FOR_LOSSLESS_PNGS",
        "acceptance_thresholds": None,
        "documents": reports,
        "errors": errors,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate real hash-locked Canva PPTX geometry semantics")
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("visual-fidelity/g2-studio-corpus-v1.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    result = run_gate(args.corpus_root, args.manifest)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
