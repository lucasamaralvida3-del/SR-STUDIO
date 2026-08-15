from __future__ import annotations

import json
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Callable


@dataclass(slots=True)
class CrashReport:
    timestamp: str
    exception_type: str
    message: str
    traceback: str
    version: str = ""
    project_path: str = ""
    safe_mode_recommended: bool = True


class CrashGuard:
    """Captura falhas não tratadas e deixa um marcador para recuperação segura."""

    def __init__(self, directory: str | Path, version: str = "") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.version = version
        self.marker = self.directory / "last_crash.json"
        self._previous = None

    def install(self, project_path_provider: Callable[[], str] | None = None) -> None:
        self._previous = sys.excepthook

        def hook(exc_type, exc, tb) -> None:
            self.capture(exc_type, exc, tb, project_path_provider() if project_path_provider else "")
            if self._previous:
                self._previous(exc_type, exc, tb)

        sys.excepthook = hook

    def uninstall(self) -> None:
        if self._previous is not None:
            sys.excepthook = self._previous
            self._previous = None

    def capture(
        self,
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
        project_path: str = "",
    ) -> CrashReport:
        report = CrashReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            exception_type=exc_type.__name__,
            message=str(exc),
            traceback="".join(traceback.format_exception(exc_type, exc, tb)),
            version=self.version,
            project_path=project_path,
        )
        self.marker.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    def last_report(self) -> CrashReport | None:
        if not self.marker.exists():
            return None
        try:
            return CrashReport(**json.loads(self.marker.read_text(encoding="utf-8-sig")))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def clear(self) -> None:
        self.marker.unlink(missing_ok=True)

    def should_offer_safe_mode(self) -> bool:
        report = self.last_report()
        return bool(report and report.safe_mode_recommended)
