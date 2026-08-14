from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from data.v5_store import (
    AUTOSAVE_DIR,
    PROJECTS_DIR,
    RECOVERY_DIR,
    VERSIONS_DIR,
    atomic_json,
    connection,
    json_dumps,
    json_loads,
    now_iso,
    uid,
)

PROJECT_FORMAT = "SRSTUDIO_PROJECT_2"
PACKAGE_FORMAT = "SRSTUDIO_PROJECT_PACKAGE_1"


def _safe_name(value: str, fallback: str = "projeto") -> str:
    import re
    text = re.sub(r"[^A-Za-z0-9À-ÿ._ -]+", "_", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return text[:90] or fallback


def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def _autosave_file(project_id: str) -> Path:
    return AUTOSAVE_DIR / f"{project_id}.autosave.json"


def _default_payload(project_id: str, name: str, campaign: str = "") -> dict[str, Any]:
    now = now_iso()
    return {
        "format": PROJECT_FORMAT,
        "project_id": project_id,
        "name": name,
        "campaign": campaign,
        "created_at": now,
        "updated_at": now,
        "revision": 1,
        "state": {
            "products": [],
            "pages": [],
            "template_profile_id": "",
            "spreadsheet_profile_id": "",
            "source_spreadsheet": "",
            "source_template": "",
            "export_profile_id": "",
            "campaign_settings": {},
        },
        "assets": [],
        "notes": "",
    }


def create_project(name: str, campaign: str = "", state: dict[str, Any] | None = None) -> dict[str, Any]:
    project_id = uid("proj")
    payload = _default_payload(project_id, str(name or "Novo Projeto").strip() or "Novo Projeto", campaign)
    if isinstance(state, dict):
        payload["state"].update(state)
    folder = _project_dir(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    file_path = _project_file(project_id)
    atomic_json(file_path, payload)
    now = now_iso()
    with connection() as con:
        con.execute(
            """INSERT INTO projects(id,name,campaign,status,file_path,archived,created_at,updated_at,last_opened,metadata_json)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (project_id, payload["name"], campaign, "ATIVO", str(file_path), 0, now, now, now, "{}"),
        )
    return payload


def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("format") not in {PROJECT_FORMAT, "SR_STUDIO_ENCARTES_PROJECT_1"}:
        raise ValueError("Arquivo não é um projeto válido do SR Studio.")
    if payload.get("format") == "SR_STUDIO_ENCARTES_PROJECT_1":
        state = payload.get("state") or {}
        project_id = uid("proj")
        converted = _default_payload(project_id, str(state.get("projectName") or "Encarte importado"), "ENCARTE")
        converted["state"]["encartes_state"] = state
        converted["state"]["products"] = state.get("products") or []
        converted["state"]["pages"] = state.get("pages") or []
        converted["legacy"] = {"format": payload.get("format"), "version": payload.get("version")}
        return converted
    if not payload.get("project_id"):
        payload["project_id"] = uid("proj")
    if not isinstance(payload.get("state"), dict):
        payload["state"] = {}
    return payload


def list_projects(include_archived: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM projects"
    params: tuple[Any, ...] = ()
    if not include_archived:
        sql += " WHERE archived=0"
    sql += " ORDER BY last_opened DESC,updated_at DESC,name COLLATE NOCASE"
    with connection() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def project_record(project_id: str) -> dict[str, Any] | None:
    with connection() as con:
        r = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return dict(r) if r else None


def load_project(project_id: str, prefer_autosave: bool = False) -> dict[str, Any]:
    rec = project_record(project_id)
    if not rec:
        raise FileNotFoundError("Projeto não encontrado.")
    saved = Path(rec["file_path"])
    auto = _autosave_file(project_id)
    chosen = auto if prefer_autosave and auto.exists() else saved
    if not chosen.exists():
        raise FileNotFoundError(f"Arquivo do projeto não encontrado: {chosen}")
    payload = _validate_payload(json.loads(chosen.read_text(encoding="utf-8-sig")))
    with connection() as con:
        con.execute("UPDATE projects SET last_opened=? WHERE id=?", (now_iso(), project_id))
    return payload


def save_project(payload: dict[str, Any], autosave: bool = False, create_version: bool = False, label: str = "") -> dict[str, Any]:
    payload = _validate_payload(dict(payload))
    project_id = str(payload["project_id"])
    payload["updated_at"] = now_iso()
    payload["revision"] = int(payload.get("revision") or 0) + 1

    if autosave:
        target = _autosave_file(project_id)
        payload["autosave_at"] = now_iso()
        atomic_json(target, payload)
        return payload

    folder = _project_dir(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = _project_file(project_id)
    atomic_json(target, payload)
    try:
        _autosave_file(project_id).unlink(missing_ok=True)
    except Exception:
        pass

    now = now_iso()
    with connection() as con:
        con.execute(
            """INSERT INTO projects(id,name,campaign,status,file_path,archived,created_at,updated_at,last_opened,metadata_json)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,campaign=excluded.campaign,file_path=excluded.file_path,
                    updated_at=excluded.updated_at,last_opened=excluded.last_opened""",
            (
                project_id,
                str(payload.get("name") or "Novo Projeto"),
                str(payload.get("campaign") or ""),
                "ATIVO",
                str(target),
                0,
                str(payload.get("created_at") or now),
                now,
                now,
                json_dumps({"revision": payload["revision"]}),
            ),
        )
    if create_version:
        snapshot_project(project_id, label or f"Versão {payload['revision']}")
    return payload


def snapshot_project(project_id: str, label: str = "", is_auto: bool = False) -> dict[str, Any]:
    payload = load_project(project_id, prefer_autosave=False)
    version_id = uid("ver")
    folder = VERSIONS_DIR / project_id
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = folder / f"{stamp}_{version_id}.json"
    atomic_json(path, payload)
    item = {
        "id": version_id,
        "project_id": project_id,
        "label": str(label or f"Versão {stamp}"),
        "snapshot_path": str(path),
        "is_auto": 1 if is_auto else 0,
        "created_at": now_iso(),
    }
    with connection() as con:
        con.execute(
            "INSERT INTO project_versions(id,project_id,label,snapshot_path,is_auto,created_at) VALUES(?,?,?,?,?,?)",
            tuple(item[k] for k in ("id", "project_id", "label", "snapshot_path", "is_auto", "created_at")),
        )
        # Mantém até 30 versões por projeto, priorizando versões manuais.
        old = con.execute(
            """SELECT id,snapshot_path FROM project_versions WHERE project_id=?
               ORDER BY is_auto ASC,created_at DESC LIMIT -1 OFFSET 30""",
            (project_id,),
        ).fetchall()
        for r in old:
            try:
                Path(r["snapshot_path"]).unlink(missing_ok=True)
            except Exception:
                pass
            con.execute("DELETE FROM project_versions WHERE id=?", (r["id"],))
    return item


def list_versions(project_id: str) -> list[dict[str, Any]]:
    with connection() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM project_versions WHERE project_id=? ORDER BY created_at DESC", (project_id,)
        ).fetchall()]


def restore_version(version_id: str) -> dict[str, Any]:
    with connection() as con:
        r = con.execute("SELECT * FROM project_versions WHERE id=?", (version_id,)).fetchone()
    if not r:
        raise FileNotFoundError("Versão não encontrada.")
    path = Path(r["snapshot_path"])
    payload = _validate_payload(json.loads(path.read_text(encoding="utf-8-sig")))
    snapshot_project(payload["project_id"], "Antes de restaurar", is_auto=True)
    return save_project(payload)


def duplicate_project(project_id: str, new_name: str | None = None) -> dict[str, Any]:
    src = load_project(project_id)
    state = json.loads(json.dumps(src.get("state") or {}, ensure_ascii=False))
    dup = create_project(new_name or f"{src.get('name','Projeto')} - Cópia", str(src.get("campaign") or ""), state)
    dup["notes"] = src.get("notes") or ""
    dup["assets"] = list(src.get("assets") or [])
    return save_project(dup)


def archive_project(project_id: str, archived: bool = True) -> None:
    with connection() as con:
        con.execute("UPDATE projects SET archived=?,status=?,updated_at=? WHERE id=?", (1 if archived else 0, "ARQUIVADO" if archived else "ATIVO", now_iso(), project_id))


def delete_project(project_id: str, permanent: bool = False) -> None:
    if not permanent:
        archive_project(project_id, True)
        return
    rec = project_record(project_id)
    with connection() as con:
        con.execute("DELETE FROM projects WHERE id=?", (project_id,))
    if rec:
        shutil.rmtree(Path(rec["file_path"]).parent, ignore_errors=True)
    try:
        _autosave_file(project_id).unlink(missing_ok=True)
    except Exception:
        pass
    shutil.rmtree(VERSIONS_DIR / project_id, ignore_errors=True)


def autosave_status(project_id: str) -> dict[str, Any]:
    rec = project_record(project_id)
    auto = _autosave_file(project_id)
    saved = Path(rec["file_path"]) if rec else Path()
    if not rec or not auto.exists():
        return {"recoverable": False}
    auto_m = auto.stat().st_mtime
    saved_m = saved.stat().st_mtime if saved.exists() else 0
    return {"recoverable": auto_m > saved_m, "autosave": str(auto), "saved": str(saved), "autosave_mtime": auto_m, "saved_mtime": saved_m}


def recovery_candidates() -> list[dict[str, Any]]:
    out = []
    for rec in list_projects(include_archived=False):
        info = autosave_status(rec["id"])
        if info.get("recoverable"):
            out.append({**rec, **info})
    return out


def export_project(project_id: str, output: Path) -> Path:
    payload = load_project(project_id, prefer_autosave=False)
    output = Path(output)
    if output.suffix.lower() != ".srstudio":
        output = output.with_suffix(".srstudio")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format": PACKAGE_FORMAT,
        "project_format": PROJECT_FORMAT,
        "project_id": project_id,
        "name": payload.get("name"),
        "created_at": now_iso(),
    }
    folder = _project_dir(project_id)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("project.json", json.dumps(payload, ensure_ascii=False, indent=2))
        assets = folder / "assets"
        if assets.exists():
            for path in assets.rglob("*"):
                if path.is_file():
                    zf.write(path, (Path("assets") / path.relative_to(assets)).as_posix())
    return output


def import_project(path: Path, new_name: str | None = None) -> dict[str, Any]:
    path = Path(path)
    if path.suffix.lower() == ".srstudio":
        with zipfile.ZipFile(path) as zf:
            if "project.json" not in zf.namelist():
                raise ValueError("Pacote .srstudio não contém project.json.")
            payload = _validate_payload(json.loads(zf.read("project.json").decode("utf-8-sig")))
            original_id = str(payload.get("project_id") or "")
            payload["project_id"] = uid("proj")
            payload["name"] = new_name or str(payload.get("name") or path.stem)
            payload["created_at"] = now_iso()
            payload["updated_at"] = now_iso()
            payload["imported_from"] = original_id
            folder = _project_dir(payload["project_id"])
            (folder / "assets").mkdir(parents=True, exist_ok=True)
            for name in zf.namelist():
                if not name.startswith("assets/") or name.endswith("/"):
                    continue
                rel = Path(name).relative_to("assets")
                if ".." in rel.parts:
                    continue
                target = folder / "assets" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
            return save_project(payload)

    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    converted = _validate_payload(payload)
    converted["project_id"] = uid("proj")
    converted["name"] = new_name or str(converted.get("name") or path.stem)
    converted["created_at"] = now_iso()
    converted["updated_at"] = now_iso()
    return save_project(converted)


def project_summary() -> dict[str, int]:
    with connection() as con:
        active = int(con.execute("SELECT COUNT(*) FROM projects WHERE archived=0").fetchone()[0])
        archived = int(con.execute("SELECT COUNT(*) FROM projects WHERE archived=1").fetchone()[0])
        versions = int(con.execute("SELECT COUNT(*) FROM project_versions").fetchone()[0])
    return {"active": active, "archived": archived, "versions": versions, "recoverable": len(recovery_candidates())}
