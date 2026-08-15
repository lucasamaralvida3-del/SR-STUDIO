from __future__ import annotations

import sys
from pathlib import Path

from srstudio import __channel__, __version__
from srstudio.updater.manifest import build_manifest


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: create_update_manifest.py PACKAGE OUTPUT")
        return 2
    package = Path(sys.argv[1])
    output = Path(sys.argv[2])
    manifest = build_manifest(package, __version__, __channel__, "SR Studio 5 Professional development build")
    manifest.save(output)
    print(f"manifest={output} sha256={manifest.sha256} size={manifest.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
