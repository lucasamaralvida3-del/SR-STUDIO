from __future__ import annotations

import argparse
from pathlib import Path

BLOCK = '''\n\n# SR Studio 5.0 — aprimoramentos instalados após a definição completa da Central.\nfrom ui.studio5_enhancements import install_studio5_enhancements as _install_studio5_enhancements\n_install_studio5_enhancements(Studio5Panel)\n'''


def apply(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "_install_studio5_enhancements(Studio5Panel)" in text:
        return False
    path.write_text(text.rstrip() + BLOCK, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", type=Path, default=Path("src/sr_studio/modules/Studio5Module.py"))
    args = parser.parse_args()
    print("Aprimoramentos ativados." if apply(args.path) else "Aprimoramentos já ativos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
