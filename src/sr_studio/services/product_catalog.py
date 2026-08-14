from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from SRStudio21 import PRODUCT_DB, norm, normalize_product_name, apply_learned_correction
from ProductImages import get_image_info


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(PRODUCT_DB, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=20000")
    return con


def ensure_v5_schema() -> None:
    with _conn() as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(catalog_products)").fetchall()}
        for name, sql_type in {
            "ean": "TEXT",
            "commercial_name": "TEXT",
            "brand": "TEXT",
            "notes": "TEXT",
            "quality_status": "TEXT",
            "v5_updated_at": "TEXT",
        }.items():
            if name not in cols:
                con.execute(f"ALTER TABLE catalog_products ADD COLUMN {name} {sql_type}")
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS catalog_barcodes_v5(
                ean TEXT PRIMARY KEY,
                identity_key TEXT NOT NULL,
                source TEXT DEFAULT 'MANUAL',
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_v5_barcode_identity ON catalog_barcodes_v5(identity_key);

            CREATE TABLE IF NOT EXISTS catalog_aliases_v5(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_norm TEXT NOT NULL UNIQUE,
                alias_text TEXT NOT NULL,
                identity_key TEXT NOT NULL,
                source TEXT DEFAULT 'MANUAL',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_v5_alias_identity ON catalog_aliases_v5(identity_key);

            CREATE TABLE IF NOT EXISTS catalog_audit_v5(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                source TEXT DEFAULT 'USUARIO',
                changed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_v5_audit_identity ON catalog_audit_v5(identity_key,changed_at DESC);
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_catalog_ean_v5 ON catalog_products(ean)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_catalog_commercial_v5 ON catalog_products(commercial_name)")


ensure_v5_schema()


def _image_quality(identity_key: str) -> dict[str, Any]:
    info = get_image_info(identity_key) or {}
    path = Path(str(info.get("official_path") or ""))
    result = {
        "has_image": bool(path.is_file() or info.get("official_url")),
        "image_path": str(path) if path.is_file() else "",
        "image_url": str(info.get("official_url") or ""),
        "image_width": 0,
        "image_height": 0,
        "low_resolution": False,
    }
    if path.is_file():
        try:
            from PIL import Image
            with Image.open(path) as im:
                result["image_width"], result["image_height"] = im.size
            result["low_resolution"] = min(result["image_width"], result["image_height"]) < 500
        except Exception:
            pass
    return result


def _display_name(row: dict[str, Any]) -> str:
    return str(row.get("commercial_name") or row.get("canonical_name") or "").strip()


def product_by_identity(identity_key: str) -> dict[str, Any] | None:
    ensure_v5_schema()
    with _conn() as con:
        r = con.execute("SELECT * FROM catalog_products WHERE identity_key=? LIMIT 1", (identity_key,)).fetchone()
        if not r:
            return None
        data = dict(r)
        data["aliases"] = [x[0] for x in con.execute("SELECT alias_text FROM catalog_aliases_v5 WHERE identity_key=? ORDER BY alias_text", (identity_key,)).fetchall()]
        data["barcodes"] = [x[0] for x in con.execute("SELECT ean FROM catalog_barcodes_v5 WHERE identity_key=? ORDER BY ean", (identity_key,)).fetchall()]
    data.update(_image_quality(identity_key))
    data["display_name"] = _display_name(data)
    return data


def resolve_product(code: str = "", name: str = "", ean: str = "") -> dict[str, Any] | None:
    ensure_v5_schema()
    code = str(code or "").strip()
    ean = re.sub(r"\D+", "", str(ean or ""))
    target = norm(name)
    identity = ""
    with _conn() as con:
        if ean:
            r = con.execute("SELECT identity_key FROM catalog_barcodes_v5 WHERE ean=?", (ean,)).fetchone()
            if r:
                identity = str(r[0])
        if not identity and code:
            r = con.execute("SELECT identity_key FROM catalog_products WHERE active=1 AND (codigo=? OR codigo_ciss=?) LIMIT 1", (code, code)).fetchone()
            if r:
                identity = str(r[0])
        if not identity and target:
            r = con.execute("SELECT identity_key FROM catalog_aliases_v5 WHERE alias_norm=?", (target,)).fetchone()
            if r:
                identity = str(r[0])
        if not identity and target:
            r = con.execute("SELECT identity_key FROM catalog_products WHERE active=1 AND (canonical_norm=? OR UPPER(commercial_name)=?) LIMIT 1", (target, str(name or "").upper())).fetchone()
            if r:
                identity = str(r[0])
    return product_by_identity(identity) if identity else None


def search_products(query: str = "", limit: int = 200, only_issues: bool = False) -> list[dict[str, Any]]:
    ensure_v5_schema()
    q = str(query or "").strip()
    nq = norm(q)
    params: list[Any] = []
    where = ["p.active=1"]
    if q:
        where.append("(p.codigo LIKE ? OR p.codigo_ciss LIKE ? OR p.ean LIKE ? OR p.canonical_norm LIKE ? OR UPPER(COALESCE(p.commercial_name,'')) LIKE ? OR EXISTS(SELECT 1 FROM catalog_aliases_v5 a WHERE a.identity_key=p.identity_key AND a.alias_norm LIKE ?))")
        like_raw = f"%{q}%"
        like_norm = f"%{nq}%"
        params.extend([like_raw, like_raw, like_raw, like_norm, like_norm, like_norm])
    sql = "SELECT p.* FROM catalog_products p WHERE " + " AND ".join(where) + " ORDER BY COALESCE(NULLIF(p.commercial_name,''),p.canonical_name) COLLATE NOCASE LIMIT ?"
    params.append(max(1, min(2000, int(limit))))
    with _conn() as con:
        items = [dict(r) for r in con.execute(sql, params).fetchall()]
    result = []
    for item in items:
        quality = _image_quality(str(item.get("identity_key") or ""))
        item.update(quality)
        item["display_name"] = _display_name(item)
        issues = []
        if not item.get("commercial_name"):
            issues.append("SEM_NOME_COMERCIAL")
        if not item.get("categoria"):
            issues.append("SEM_CATEGORIA")
        if not quality["has_image"]:
            issues.append("SEM_IMAGEM")
        elif quality["low_resolution"]:
            issues.append("IMAGEM_BAIXA_RESOLUCAO")
        if not (item.get("ean") or item.get("codigo") or item.get("codigo_ciss")):
            issues.append("SEM_CODIGO")
        item["quality_issues"] = issues
        item["quality_status"] = "OK" if not issues else "REVISAR"
        if not only_issues or issues:
            result.append(item)
    return result


def _audit(con: sqlite3.Connection, identity: str, field: str, old: Any, new: Any, source: str) -> None:
    if str(old or "") == str(new or ""):
        return
    con.execute(
        "INSERT INTO catalog_audit_v5(identity_key,field,old_value,new_value,source,changed_at) VALUES(?,?,?,?,?,?)",
        (identity, field, str(old or ""), str(new or ""), source, _now()),
    )


def update_product(identity_key: str, *, commercial_name: str | None = None, ean: str | None = None, brand: str | None = None, category: str | None = None, unit: str | None = None, notes: str | None = None, source: str = "USUARIO") -> dict[str, Any]:
    ensure_v5_schema()
    with _conn() as con:
        row = con.execute("SELECT * FROM catalog_products WHERE identity_key=?", (identity_key,)).fetchone()
        if not row:
            raise KeyError("Produto não encontrado no Banco de Produtos.")
        current = dict(row)
        patch: dict[str, Any] = {}
        if commercial_name is not None:
            patch["commercial_name"] = normalize_product_name(apply_learned_correction(commercial_name)) if commercial_name.strip() else ""
        if brand is not None:
            patch["brand"] = str(brand).strip().upper()
        if category is not None:
            patch["categoria"] = str(category).strip().upper()
        if unit is not None:
            patch["unidade"] = str(unit).strip().upper()
        if notes is not None:
            patch["notes"] = str(notes).strip()
        clean_ean = re.sub(r"\D+", "", str(ean or "")) if ean is not None else None
        if clean_ean is not None:
            patch["ean"] = clean_ean
        patch["v5_updated_at"] = _now()
        for field, value in patch.items():
            _audit(con, identity_key, field, current.get(field), value, source)
        assignments = ",".join(f"{k}=?" for k in patch)
        con.execute(f"UPDATE catalog_products SET {assignments} WHERE identity_key=?", (*patch.values(), identity_key))
        if clean_ean:
            con.execute(
                "INSERT INTO catalog_barcodes_v5(ean,identity_key,source,updated_at) VALUES(?,?,?,?) ON CONFLICT(ean) DO UPDATE SET identity_key=excluded.identity_key,source=excluded.source,updated_at=excluded.updated_at",
                (clean_ean, identity_key, source, _now()),
            )
    return product_by_identity(identity_key) or {}


def add_alias(identity_key: str, alias: str, source: str = "USUARIO") -> None:
    alias_text = normalize_product_name(alias)
    alias_norm = norm(alias_text)
    if not alias_norm:
        return
    with _conn() as con:
        if not con.execute("SELECT 1 FROM catalog_products WHERE identity_key=?", (identity_key,)).fetchone():
            raise KeyError("Produto não encontrado.")
        con.execute(
            """INSERT INTO catalog_aliases_v5(alias_norm,alias_text,identity_key,source,created_at,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(alias_norm) DO UPDATE SET alias_text=excluded.alias_text,identity_key=excluded.identity_key,source=excluded.source,updated_at=excluded.updated_at""",
            (alias_norm, alias_text, identity_key, source, _now(), _now()),
        )


def remove_alias(alias: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM catalog_aliases_v5 WHERE alias_norm=?", (norm(alias),))


def audit_history(identity_key: str, limit: int = 100) -> list[dict[str, Any]]:
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM catalog_audit_v5 WHERE identity_key=? ORDER BY changed_at DESC,id DESC LIMIT ?", (identity_key, int(limit))).fetchall()]


def quality_summary() -> dict[str, int]:
    items = search_products("", limit=2000)
    return {
        "total": len(items),
        "ok": sum(1 for x in items if not x["quality_issues"]),
        "without_image": sum(1 for x in items if "SEM_IMAGEM" in x["quality_issues"]),
        "low_resolution": sum(1 for x in items if "IMAGEM_BAIXA_RESOLUCAO" in x["quality_issues"]),
        "without_commercial_name": sum(1 for x in items if "SEM_NOME_COMERCIAL" in x["quality_issues"]),
        "without_category": sum(1 for x in items if "SEM_CATEGORIA" in x["quality_issues"]),
    }
