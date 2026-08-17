from __future__ import annotations

"""CLI gate for validating whether a .srscene is structurally safe for flyer editing."""

from argparse import ArgumentParser
from pathlib import Path
import json

from srstudio.graphics2.package import load_package
from srstudio.graphics2.usability_gate import inspect_g2_usability


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="g2-usability-check",
        description="Valida segurança estrutural e prontidão de edição do Studio de Encartes G2.",
    )
    parser.add_argument("scene", type=Path, help="Pacote .srscene/.zip do Graphics Engine 2.")
    parser.add_argument(
        "--require-multi-product",
        action="store_true",
        help="Exige ao menos uma página com dois ou mais ProductCards/Smart Slots.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emite somente JSON para CI/automação.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    document = load_package(args.scene)
    report = inspect_g2_usability(
        document,
        require_multi_product_page=bool(args.require_multi_product),
    )
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        status = "PASS" if report.professional_usable else "BLOCKED"
        print(f"G2 PROFESSIONAL USABILITY: {status}")
        print(
            "pages={page_count} populated={populated_pages} nodes={node_count} "
            "slots={smart_slots} bound={bound_slots} cards={product_cards} prices={price_blocks}".format(**payload)
        )
        for issue in report.issues:
            suffix = ""
            if issue.page_id:
                suffix += f" page={issue.page_id}"
            if issue.object_id:
                suffix += f" object={issue.object_id}"
            print(f"[{issue.severity.upper()}] {issue.code}: {issue.message}{suffix}")
    return 0 if report.professional_usable else 2


if __name__ == "__main__":
    raise SystemExit(main())
