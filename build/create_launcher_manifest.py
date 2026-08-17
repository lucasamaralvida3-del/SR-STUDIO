from __future__ import annotations

"""Gera o manifesto SHA-256 do Bootstrap/Launcher e componentes auxiliares.

Evita editar hashes e tamanhos manualmente quando o Bootstrap ou o updater do
Graphics2Host mudam. O manifesto gerado pode ser comparado ao arquivo versionado
antes de publicar Stable/Beta.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "manifests" / "launcher.json"
FILES = (
    "SRStudioLauncher.ps1",
    "SRStudioBootstrap.ps1",
    "SRGraphics2Component.ps1",
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _constant(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8-sig")
    match = re.search(rf"\${re.escape(name)}\s*=\s*'([^']+)'", text)
    if not match:
        raise ValueError(f"Constante ${name} não encontrada em {path.name}.")
    return match.group(1)


def build_launcher_manifest(*, published_at: str | None = None) -> dict[str, object]:
    files_dir = ROOT / "launcher" / "files"
    launcher = files_dir / "SRStudioLauncher.ps1"
    bootstrap = files_dir / "SRStudioBootstrap.ps1"
    launcher_version = _constant(launcher, "LauncherVersion")
    bootstrap_version = _constant(bootstrap, "BootstrapVersion")
    entries: list[dict[str, object]] = []
    for name in FILES:
        path = files_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        entries.append(
            {
                "path": name,
                "source": f"launcher/files/{name}",
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return {
        "format": "SRSTUDIO_LAUNCHER_MANIFEST_1",
        "product": "SR Studio Launcher",
        "version": f"{launcher_version}+{bootstrap_version}",
        "launcher_version": launcher_version,
        "bootstrap_version": bootstrap_version,
        "published_at": published_at or datetime.now(timezone.utc).isoformat(),
        "files": entries,
    }


def normalized_payload(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    result.pop("published_at", None)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Gera manifests/launcher.json com SHA-256 e tamanho reais.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path, default=None, help="Compara conteúdo funcional, ignorando published_at.")
    parser.add_argument("--print", action="store_true", dest="print_json")
    args = parser.parse_args(argv)
    try:
        payload = build_launcher_manifest()
        if args.print_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.verify is not None:
            current = json.loads(args.verify.read_text(encoding="utf-8-sig"))
            if normalized_payload(current) != normalized_payload(payload):
                print("Launcher manifest: DESATUALIZADO", file=sys.stderr)
                print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
                return 1
            print("Launcher manifest: OK")
            return 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Launcher manifest: {args.output}")
        for entry in payload["files"]:
            print(f"  {entry['path']} · {entry['size']} bytes · {entry['sha256']}")
    except Exception as exc:
        print(f"Launcher manifest: ERRO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
