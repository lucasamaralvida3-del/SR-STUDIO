from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from EncartesPPTX import parse_pptx
from data.v5_store import TEMPLATES_DIR, connection, json_dumps, json_loads, now_iso, uid

FIELD_ROLES = (
    "",
    "IMAGEM",
    "NOME",
    "PRECO_RS",
    "PRECO_REAIS",
    "PRECO_CENTAVOS",
    "UNIDADE",
    "PRECO_APP",
    "LIMITE",
    "TEXTO_FIXO",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_template(path: Path, profile_id: str) -> Path:
    folder = TEMPLATES_DIR / profile_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    shutil.copy2(path, target)
    return target


def analyze_template(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    data = path.read_bytes()
    parsed = parse_pptx(data, path.name)
    shapes = []
    for page_index, page in enumerate(parsed.get("pages") or [], 1):
        for element in page.get("templateElements") or []:
            shapes.append(
                {
                    "key": f"p{page_index}:{element.get('pptxId') or element.get('id')}",
                    "page": page_index,
                    "pptx_id": element.get("pptxId") or 0,
                    "element_id": element.get("id") or "",
                    "type": element.get("type") or "",
                    "name": element.get("name") or "",
                    "text": element.get("text") or "",
                    "detected_role": element.get("role") or ("IMAGEM" if element.get("imageCandidate") else ""),
                    "x": element.get("x", 0),
                    "y": element.get("y", 0),
                    "w": element.get("w", 0),
                    "h": element.get("h", 0),
                }
            )
    return {
        "source": path.name,
        "source_hash": sha256_bytes(data),
        "page_count": int(parsed.get("pageCount") or 0),
        "slot_count": int(parsed.get("slotCount") or 0),
        "auto_image_slot_count": int(parsed.get("autoImageSlotCount") or 0),
        "visual_mode": parsed.get("visualMode") or "",
        "visual_warning": parsed.get("visualWarning") or "",
        "shapes": shapes,
        "parsed": parsed,
    }


def detected_mapping(analysis: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for shape in analysis.get("shapes") or []:
        role = str(shape.get("detected_role") or "")
        if role in FIELD_ROLES and role:
            mapping[str(shape.get("key"))] = role
    return mapping


def save_template(name: str, campaign: str, source_path: str | Path, analysis: dict[str, Any] | None = None, mapping: dict[str, str] | None = None, profile_id: str = "") -> dict[str, Any]:
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    analysis = analysis or analyze_template(source)
    source_hash = str(analysis.get("source_hash") or sha256_file(source))
    existing = find_by_hash(source_hash)
    pid = profile_id or (existing.get("id") if existing else "") or uid("tpl")
    target = _copy_template(source, pid)
    mapping = mapping or detected_mapping(analysis)
    clean_mapping = {str(k): str(v) for k, v in mapping.items() if str(v) in FIELD_ROLES}
    # Não grava dados transitórios grandes do render local; apenas o necessário para reaprender.
    stored_analysis = {
        "source": analysis.get("source") or source.name,
        "source_hash": source_hash,
        "page_count": analysis.get("page_count", 0),
        "slot_count": analysis.get("slot_count", 0),
        "auto_image_slot_count": analysis.get("auto_image_slot_count", 0),
        "visual_mode": analysis.get("visual_mode", ""),
        "visual_warning": analysis.get("visual_warning", ""),
        "shapes": analysis.get("shapes") or [],
    }
    now = now_iso()
    with connection() as con:
        con.execute(
            """INSERT INTO template_profiles(id,name,campaign,source_name,source_hash,template_path,mapping_json,analysis_json,created_at,updated_at,last_used)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,campaign=excluded.campaign,source_name=excluded.source_name,
                 source_hash=excluded.source_hash,template_path=excluded.template_path,mapping_json=excluded.mapping_json,
                 analysis_json=excluded.analysis_json,updated_at=excluded.updated_at""",
            (pid, str(name or source.stem).strip(), str(campaign or "").strip(), source.name, source_hash, str(target), json_dumps(clean_mapping), json_dumps(stored_analysis), now, now, now),
        )
    return get_template(pid) or {}


def _decode(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["mapping"] = json_loads(d.pop("mapping_json", "{}"), {})
    d["analysis"] = json_loads(d.pop("analysis_json", "{}"), {})
    return d


def get_template(profile_id: str) -> dict[str, Any] | None:
    with connection() as con:
        r = con.execute("SELECT * FROM template_profiles WHERE id=?", (profile_id,)).fetchone()
    return _decode(r) if r else None


def find_by_hash(source_hash: str) -> dict[str, Any] | None:
    with connection() as con:
        r = con.execute("SELECT * FROM template_profiles WHERE source_hash=? LIMIT 1", (source_hash,)).fetchone()
    return _decode(r) if r else None


def list_templates(campaign: str = "") -> list[dict[str, Any]]:
    with connection() as con:
        if campaign:
            rows = con.execute("SELECT * FROM template_profiles WHERE campaign=? ORDER BY last_used DESC,name COLLATE NOCASE", (campaign,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM template_profiles ORDER BY last_used DESC,updated_at DESC,name COLLATE NOCASE").fetchall()
    return [_decode(r) for r in rows]


def update_mapping(profile_id: str, mapping: dict[str, str]) -> dict[str, Any]:
    clean = {str(k): str(v) for k, v in mapping.items() if str(v) in FIELD_ROLES}
    with connection() as con:
        con.execute("UPDATE template_profiles SET mapping_json=?,updated_at=? WHERE id=?", (json_dumps(clean), now_iso(), profile_id))
    return get_template(profile_id) or {}


def delete_template(profile_id: str) -> None:
    item = get_template(profile_id)
    with connection() as con:
        con.execute("DELETE FROM template_profiles WHERE id=?", (profile_id,))
    if item:
        try:
            shutil.rmtree(Path(item["template_path"]).parent, ignore_errors=True)
        except Exception:
            pass


def apply_mapping(parsed: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Reaplica o mapeamento aprendido a uma análise nova do mesmo PPTX."""
    for page_index, page in enumerate(parsed.get("pages") or [], 1):
        for element in page.get("templateElements") or []:
            key = f"p{page_index}:{element.get('pptxId') or element.get('id')}"
            role = mapping.get(key)
            if role in FIELD_ROLES:
                element["role"] = role
        # O algoritmo existente de slots entende os roles; a reconstrução completa dos slots
        # será feita pelo editor ao carregar o template aprendido.
    return parsed


def load_learned_template(profile_id: str) -> dict[str, Any]:
    profile = get_template(profile_id)
    if not profile:
        raise KeyError("Modelo aprendido não encontrado.")
    path = Path(profile["template_path"])
    if not path.is_file():
        raise FileNotFoundError(path)
    parsed = parse_pptx(path.read_bytes(), path.name)
    apply_mapping(parsed, profile.get("mapping") or {})
    with connection() as con:
        con.execute("UPDATE template_profiles SET last_used=? WHERE id=?", (now_iso(), profile_id))
    return {"profile": profile, "parsed": parsed}


def template_summary() -> dict[str, int]:
    with connection() as con:
        total = int(con.execute("SELECT COUNT(*) FROM template_profiles").fetchone()[0])
        mapped = int(con.execute("SELECT COUNT(*) FROM template_profiles WHERE mapping_json NOT IN ('','{}')").fetchone()[0])
    return {"total": total, "mapped": mapped}
