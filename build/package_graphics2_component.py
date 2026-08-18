from __future__ import annotations

"""Cria o ZIP distribuível e o descritor `graphics2_host` do Launcher.

O build PyInstaller produz um diretório onedir. Este passo valida o catálogo
SHA-256 inteiro antes de criar o ZIP que pode ser publicado em Release/CDN. O
descritor resultante é deliberadamente `enabled=false`: o pipeline de release
precisa definir URL/source e habilitá-lo explicitamente no manifesto Beta/Stable.
"""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEFAULT_BUILD_ROOT = ROOT / "dist" / "graphics2-host"
DEFAULT_BUNDLE_NAME = "SRGraphicsEngine2Host"
COMPONENT_SCHEMA = "srstudio/graphics2-host-component-1"


@dataclass(slots=True, frozen=True)
class Graphics2HostComponent:
    schema: str
    enabled: bool
    required: bool
    platform: str
    engine_version: str
    url: str
    source: str
    sha256: str
    size: int
    member_prefix: str
    bundle_filename: str
    runtime_files: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def package_component(
    build_root: str | Path = DEFAULT_BUILD_ROOT,
    *,
    output_zip: str | Path | None = None,
    descriptor_path: str | Path | None = None,
    url: str = "",
    source: str = "",
    enabled: bool = False,
    required: bool = False,
) -> Graphics2HostComponent:
    if required and not enabled:
        raise ValueError("Componente Graphics2Host não pode ser required=true enquanto enabled=false.")
    if enabled and not (str(url).strip() or str(source).strip()):
        raise ValueError("Componente Graphics2Host habilitado precisa informar url ou source de distribuição.")

    root = Path(build_root).resolve()
    build_manifest_path = root / "graphics2-host-manifest.json"
    if not build_manifest_path.is_file():
        raise FileNotFoundError(f"Manifesto de build ausente: {build_manifest_path}")
    build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    engine_version = str(build_manifest.get("engine_version") or "")
    if not engine_version:
        raise ValueError("Manifesto de build não informa engine_version.")

    bundle = root / DEFAULT_BUNDLE_NAME
    if not bundle.is_dir():
        raise NotADirectoryError(bundle)
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    from srstudio.graphics2.host_runtime import validate_runtime_host

    validation = validate_runtime_host(bundle, full=True, expected_engine_version=engine_version)
    if not validation.ok:
        detail = validation.errors[0] if validation.errors else "falha desconhecida"
        raise RuntimeError(f"Bundle Graphics2Host rejeitado antes do ZIP: {detail}")

    zip_path = Path(output_zip).resolve() if output_zip else root / f"{DEFAULT_BUNDLE_NAME}-{engine_version}.zip"
    descriptor = (
        Path(descriptor_path).resolve()
        if descriptor_path
        else root / "graphics2-host-component.json"
    )
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(bundle.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if not path.is_file():
                continue
            relative = path.relative_to(bundle).as_posix()
            archive.write(path, arcname=f"{DEFAULT_BUNDLE_NAME}/{relative}")

    digest = _sha256_file(zip_path)
    component = Graphics2HostComponent(
        schema=COMPONENT_SCHEMA,
        enabled=bool(enabled),
        required=bool(required),
        platform="windows-x64",
        engine_version=engine_version,
        url=str(url),
        source=str(source),
        sha256=digest,
        size=zip_path.stat().st_size,
        member_prefix=DEFAULT_BUNDLE_NAME,
        bundle_filename=zip_path.name,
        runtime_files=validation.total_files,
    )
    descriptor.write_text(json.dumps(component.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Graphics2Host ZIP: {zip_path}")
    print(f"SHA-256: {digest}")
    print(f"Component descriptor: {descriptor}")
    return component


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Empacota Graphics2Host onedir para o launcher opcional.")
    parser.add_argument("--build-root", type=Path, default=DEFAULT_BUILD_ROOT)
    parser.add_argument("--output-zip", type=Path, default=None)
    parser.add_argument("--descriptor", type=Path, default=None)
    parser.add_argument("--url", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--required", action="store_true")
    args = parser.parse_args(argv)
    try:
        package_component(
            args.build_root,
            output_zip=args.output_zip,
            descriptor_path=args.descriptor,
            url=args.url,
            source=args.source,
            enabled=args.enabled,
            required=args.required,
        )
    except Exception as exc:
        print(f"Graphics2Host package: ERRO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
