from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class HealthCheck:
    key: str
    label: str
    ok: bool
    detail: str = ""
    severity: str = "info"


class HealthCenter:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def run(self, product_db: str | Path | None = None) -> list[HealthCheck]:
        checks = [
            self._directory_check(),
            self._disk_check(),
            HealthCheck("python", "Runtime Python", sys.version_info >= (3, 11), platform.python_version()),
            HealthCheck("os", "Sistema operacional", os.name == "nt", platform.platform(), "warning" if os.name != "nt" else "info"),
        ]
        if product_db:
            checks.append(self._sqlite_check(Path(product_db)))
        return checks

    def export_report(self, target: str | Path, checks: list[HealthCheck], extra: dict | None = None) -> Path:
        target = Path(target)
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "python": sys.version,
            "platform": platform.platform(),
            "checks": [asdict(item) for item in checks],
            "extra": extra or {},
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _directory_check(self) -> HealthCheck:
        try:
            probe = self.data_dir / ".health_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return HealthCheck("data-dir", "Pasta de dados", True, str(self.data_dir))
        except Exception as exc:
            return HealthCheck("data-dir", "Pasta de dados", False, str(exc), "critical")

    def _disk_check(self) -> HealthCheck:
        usage = shutil.disk_usage(self.data_dir)
        free_gb = usage.free / (1024 ** 3)
        ok = free_gb >= 1.0
        return HealthCheck("disk", "Espaço em disco", ok, f"{free_gb:.1f} GB livres", "warning" if not ok else "info")

    @staticmethod
    def _sqlite_check(path: Path) -> HealthCheck:
        try:
            with sqlite3.connect(path) as con:
                row = con.execute("PRAGMA integrity_check").fetchone()
            ok = bool(row and row[0] == "ok")
            return HealthCheck("product-db", "Banco de produtos", ok, str(row[0] if row else "sem resposta"), "critical" if not ok else "info")
        except Exception as exc:
            return HealthCheck("product-db", "Banco de produtos", False, str(exc), "critical")


def configure_logging(log_dir: str | Path, level: int = logging.INFO) -> Path:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "srstudio5.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root = logging.getLogger("srstudio")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)
    return log_path
