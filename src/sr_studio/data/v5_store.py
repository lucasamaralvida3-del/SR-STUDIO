from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

APP_DIR = Path(__file__).resolve().parents[1]
LOCAL_ROOT = Path(os.environ.get("LOCALAPPDATA", str(APP_DIR)))
LEGACY_DATA = LOCAL_ROOT / "SR_Studio_2.0"
V5_ROOT = LEGACY_DATA / "v5"
DB_PATH = V5_ROOT / "srstudio5.db"
PROJECTS_DIR = V5_ROOT / "projects"
AUTOSAVE_DIR = V5_ROOT / "autosave"
VERSIONS_DIR = V5_ROOT / "versions"
TEMPLATES_DIR = V5_ROOT / "templates"
EXPORTS_DIR = V5_ROOT / "exports"
RECOVERY_DIR = V5_ROOT / "recovery"

for _p in (V5_ROOT, PROJECTS_DIR, AUTOSAVE_DIR, VERSIONS_DIR, TEMPLATES_DIR, EXPORTS_DIR, RECOVERY_DIR):
    _p.mkdir(parents=True, exist_ok=True)

_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def uid(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def atomic_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=20000")
    return con


@contextmanager
def connection():
    with _LOCK:
        con = _connect()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def ensure_schema() -> None:
    with connection() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                campaign TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ATIVO',
                file_path TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_opened TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_v5_projects_updated ON projects(archived,updated_at DESC);

            CREATE TABLE IF NOT EXISTS project_versions(
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                label TEXT NOT NULL,
                snapshot_path TEXT NOT NULL,
                is_auto INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_v5_versions_project ON project_versions(project_id,created_at DESC);

            CREATE TABLE IF NOT EXISTS template_profiles(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                campaign TEXT DEFAULT '',
                source_name TEXT NOT NULL,
                source_hash TEXT NOT NULL UNIQUE,
                template_path TEXT NOT NULL,
                mapping_json TEXT NOT NULL DEFAULT '{}',
                analysis_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_used TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_v5_templates_campaign ON template_profiles(campaign,name);

            CREATE TABLE IF NOT EXISTS spreadsheet_profiles(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                header_signature TEXT NOT NULL,
                sheet_name TEXT DEFAULT '',
                header_row INTEGER DEFAULT 1,
                mapping_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_used TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_v5_sheet_signature ON spreadsheet_profiles(header_signature);

            CREATE TABLE IF NOT EXISTS export_profiles(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                format TEXT NOT NULL,
                width_px INTEGER DEFAULT 0,
                height_px INTEGER DEFAULT 0,
                dpi INTEGER DEFAULT 96,
                page_size TEXT DEFAULT '',
                options_json TEXT NOT NULL DEFAULT '{}',
                builtin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_snapshots(
                id TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                channel TEXT DEFAULT '',
                label TEXT NOT NULL,
                backup_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS v5_meta(
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )


ensure_schema()


def rows(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connection() as con:
        return [dict(r) for r in con.execute(sql, tuple(params)).fetchall()]


def row(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    with connection() as con:
        item = con.execute(sql, tuple(params)).fetchone()
        return dict(item) if item is not None else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connection() as con:
        cur = con.execute(sql, tuple(params))
        return int(cur.rowcount or 0)


def get_meta(key: str, default: str = "") -> str:
    item = row("SELECT value FROM v5_meta WHERE key=?", (key,))
    return str(item.get("value") if item else default)


def set_meta(key: str, value: Any) -> None:
    with connection() as con:
        con.execute(
            "INSERT INTO v5_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(key), str(value)),
        )


def health() -> dict[str, Any]:
    ensure_schema()
    result = {"database": str(DB_PATH), "exists": DB_PATH.exists(), "root": str(V5_ROOT)}
    with connection() as con:
        for table in ("projects", "project_versions", "template_profiles", "spreadsheet_profiles", "export_profiles"):
            result[table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return result
