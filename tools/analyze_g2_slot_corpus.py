from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from srstudio.graphics2.import_bridge import GraphicsImportService
from srstudio.graphics2.slot_corpus_ground_truth import extract_slot_corpus_ground_truth


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a real Canva/PPTX flyer and emit supervised G2 ItemSlot/ProductCard evidence."
    )
    parser.add_argument("source", type=Path, help="Real PPTX/Canva export used as ground truth")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/g2-slot-corpus-ground-truth.json"),
        help="JSON evidence report",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Corpus file not found: {source}")

    digest = _sha256(source)
    imported = GraphicsImportService().import_file(source, project_name=f"Corpus · {source.stem}")
    payload = extract_slot_corpus_ground_truth(
        imported.document,
        source_name=source.name,
        source_sha256=digest,
    )
    payload["import_summary"] = {
        "products_added": imported.summary.products_added,
        "cards_added": imported.summary.cards_added,
        "images_matched": imported.summary.images_matched,
        "images_learned": imported.summary.images_learned,
        "layouts_learned": imported.summary.layouts_learned,
        "warnings": list(imported.summary.warnings),
    }

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "source": source.name,
                "source_sha256": digest,
                "pages_analyzed": payload["pages_analyzed"],
                "product_cards": payload["product_cards"],
                "slot_families": payload["slot_families"],
                "product_image_associations": len(payload["product_image_associations"]),
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
