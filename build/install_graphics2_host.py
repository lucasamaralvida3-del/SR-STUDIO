from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import sys

from srstudio.graphics2 import ENGINE_VERSION
from srstudio.graphics2.host_install import (
    default_install_dir,
    install_verified_host,
    read_install_receipt,
    rollback_host_install,
)


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Instala/valida o host isolado do SR Graphics Engine 2.")
    sub = parser.add_subparsers(dest="command", required=True)

    install = sub.add_parser("install", help="Instala um bundle já construído e validado.")
    install.add_argument("bundle", type=Path)
    install.add_argument("--dest", type=Path, default=None)
    install.add_argument("--discard-previous", action="store_true")

    rollback = sub.add_parser("rollback", help="Restaura Graphics2Host.previous.")
    rollback.add_argument("--dest", type=Path, default=None)

    status = sub.add_parser("status", help="Mostra o receipt da instalação atual.")
    status.add_argument("--dest", type=Path, default=None)

    args = parser.parse_args(argv)
    try:
        destination = args.dest.resolve() if args.dest is not None else default_install_dir()
        if args.command == "install":
            result = install_verified_host(
                args.bundle,
                install_dir=destination,
                expected_engine_version=ENGINE_VERSION,
                keep_previous=not args.discard_previous,
            )
            print(result.message)
            if result.ok:
                print(f"Destino: {result.install_dir}")
                if result.previous_dir:
                    print(f"Rollback: {result.previous_dir}")
                return 0
            return 2

        if args.command == "rollback":
            result = rollback_host_install(destination)
            print(result.message)
            return 0 if result.ok else 2

        receipt = read_install_receipt(destination)
        if receipt is None:
            print(f"Host Graphics Engine 2 não instalado em {destination}.")
            return 1
        print(f"Graphics Engine 2 Host {receipt.engine_version}")
        print(f"Instalado em: {receipt.installed_at_utc}")
        print(f"Executável: {receipt.executable}")
        print(f"Arquivos catalogados: {receipt.files}")
        print(f"SHA-256: {receipt.executable_sha256}")
        return 0
    except Exception as exc:
        print(f"Graphics Engine 2 host install: ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
