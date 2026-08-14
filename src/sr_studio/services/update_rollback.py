from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from data.v5_store import RECOVERY_DIR, connection, json_dumps, json_loads, now_iso, uid

APP_DIR = Path(__file__).resolve().parents[1]
LOCAL_ROOT = Path(os.environ.get("LOCALAPPDATA", str(APP_DIR)))
INSTALL_ROOT = LOCAL_ROOT / "SRStudio"
CONFIG_DIR = INSTALL_ROOT / "Config"
INSTALLED_FILE = CONFIG_DIR / "installed.json"
LAUNCHER_CONFIG = CONFIG_DIR / "launcher.json"
UPDATE_HISTORY = LOCAL_ROOT / "SR_Studio_2.0" / "update_history.json"
LEGACY_BACKUPS = APP_DIR / "atualizacoes" / "backups"


def installed_info() -> dict[str, Any]:
    out = {"version": "", "channel": "", "release_label": "", "installed_file": str(INSTALLED_FILE)}
    for path in (INSTALLED_FILE, APP_DIR / "version.json", LAUNCHER_CONFIG):
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            out["version"] = str(data.get("distribution_version") or data.get("version") or out["version"])
            out["channel"] = str(data.get("channel") or out["channel"])
            out["release_label"] = str(data.get("release_label") or out["release_label"])
            if path == INSTALLED_FILE:
                break
        except Exception:
            continue
    return out


def update_history() -> list[dict[str, Any]]:
    try:
        data = json.loads(UPDATE_HISTORY.read_text(encoding="utf-8-sig")) if UPDATE_HISTORY.exists() else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def discover_backups() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    history = update_history()
    for item in history:
        path = Path(str(item.get("backup") or ""))
        if path.is_dir():
            records.append({
                "id": str(path),
                "path": str(path),
                "from": str(item.get("from") or ""),
                "to": str(item.get("to") or ""),
                "date": str(item.get("date") or ""),
                "source": "HISTORICO",
            })
    if LEGACY_BACKUPS.is_dir():
        known = {x["path"] for x in records}
        for path in sorted(LEGACY_BACKUPS.iterdir(), reverse=True):
            if path.is_dir() and str(path) not in known:
                records.append({"id": str(path), "path": str(path), "from": "", "to": "", "date": path.name, "source": "BACKUP_LOCAL"})
    return records


def create_app_snapshot(label: str = "Snapshot manual", source_dir: str | Path | None = None) -> dict[str, Any]:
    source = Path(source_dir) if source_dir else APP_DIR
    version = installed_info()
    sid = uid("snap")
    target = RECOVERY_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{sid}"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "atualizacoes", "dados")
    shutil.copytree(source, target, ignore=ignore)
    item = {
        "id": sid,
        "version": version.get("version") or "desconhecida",
        "channel": version.get("channel") or "",
        "label": str(label or "Snapshot manual"),
        "backup_path": str(target),
        "created_at": now_iso(),
        "metadata": {"source": str(source)},
    }
    with connection() as con:
        con.execute(
            "INSERT INTO app_snapshots(id,version,channel,label,backup_path,created_at,metadata_json) VALUES(?,?,?,?,?,?,?)",
            (item["id"], item["version"], item["channel"], item["label"], item["backup_path"], item["created_at"], json_dumps(item["metadata"])),
        )
    return item


def list_snapshots() -> list[dict[str, Any]]:
    with connection() as con:
        rows = con.execute("SELECT * FROM app_snapshots ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json_loads(d.pop("metadata_json", "{}"), {})
        d["exists"] = Path(d["backup_path"]).is_dir()
        out.append(d)
    return out


def _safe_files(root: Path) -> list[Path]:
    result = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in {"dados", "__pycache__", "v5"} for part in rel.parts):
            continue
        if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            continue
        result.append(path)
    return result


def restore_snapshot(snapshot_id: str, app_dir: str | Path | None = None) -> dict[str, Any]:
    app_dir = Path(app_dir) if app_dir else APP_DIR
    with connection() as con:
        r = con.execute("SELECT * FROM app_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    if not r:
        raise KeyError("Snapshot não encontrado.")
    source = Path(r["backup_path"])
    if not source.is_dir():
        raise FileNotFoundError(source)
    guard = create_app_snapshot("Antes do rollback", app_dir)
    restored = 0
    for src in _safe_files(source):
        rel = src.relative_to(source)
        dst = app_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".rollback_tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
        restored += 1
    return {"restored": restored, "snapshot": dict(r), "guard_snapshot": guard}


def status() -> dict[str, Any]:
    return {
        "installed": installed_info(),
        "update_history": update_history()[-20:],
        "legacy_backups": discover_backups()[:20],
        "snapshots": list_snapshots()[:20],
    }
