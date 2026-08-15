from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass(slots=True)
class ProductRecord:
    code: str = ""
    ean: str = ""
    name: str = ""
    display_name: str = ""
    category: str = ""
    unit: str = "UN"
    image_path: str = ""
    last_price: str = ""
    metadata: dict | None = None


class ProductDatabase:
    """Banco local desacoplado do CISS, preparado para histórico e reconhecimento."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init_schema(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS products(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT,
                    ean TEXT,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    category TEXT,
                    unit TEXT,
                    image_path TEXT,
                    last_price TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_products_ean ON products(ean) WHERE ean <> '';
                CREATE INDEX IF NOT EXISTS ix_products_code ON products(code);
                CREATE INDEX IF NOT EXISTS ix_products_name ON products(name);
                CREATE TABLE IF NOT EXISTS price_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_key TEXT NOT NULL,
                    price TEXT NOT NULL,
                    campaign TEXT,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_price_product ON price_history(product_key, recorded_at DESC);
                """
            )

    def upsert(self, record: ProductRecord) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        metadata = json.dumps(record.metadata or {}, ensure_ascii=False)
        with self.connect() as con:
            if record.ean:
                row = con.execute("SELECT id FROM products WHERE ean=?", (record.ean,)).fetchone()
            elif record.code:
                row = con.execute("SELECT id FROM products WHERE code=? ORDER BY id LIMIT 1", (record.code,)).fetchone()
            else:
                row = con.execute("SELECT id FROM products WHERE name=? ORDER BY id LIMIT 1", (record.name,)).fetchone()
            if row:
                con.execute(
                    """UPDATE products SET code=?, ean=?, name=?, display_name=?, category=?, unit=?, image_path=?, last_price=?, metadata_json=?, updated_at=? WHERE id=?""",
                    (record.code, record.ean, record.name, record.display_name, record.category, record.unit, record.image_path, record.last_price, metadata, now, row["id"]),
                )
                return int(row["id"])
            cur = con.execute(
                """INSERT INTO products(code,ean,name,display_name,category,unit,image_path,last_price,metadata_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (record.code, record.ean, record.name, record.display_name, record.category, record.unit, record.image_path, record.last_price, metadata, now),
            )
            return int(cur.lastrowid)

    def bulk_upsert(self, records: Iterable[ProductRecord]) -> int:
        count = 0
        for record in records:
            self.upsert(record)
            count += 1
        return count

    def search(self, query: str, limit: int = 100) -> list[dict]:
        value = f"%{query.strip()}%"
        if value == "%%":
            return []
        with self.connect() as con:
            rows = con.execute(
                """SELECT * FROM products WHERE code LIKE ? OR ean LIKE ? OR name LIKE ? OR display_name LIKE ? OR category LIKE ? ORDER BY updated_at DESC LIMIT ?""",
                (value, value, value, value, value, int(limit)),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def price_history(self, product_key: str, limit: int = 20) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT price,campaign,recorded_at FROM price_history WHERE product_key=? ORDER BY recorded_at DESC LIMIT ?",
                (product_key, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_price(self, product_key: str, price: str, campaign: str = "") -> None:
        if not product_key or not price:
            return
        with self.connect() as con:
            con.execute(
                "INSERT INTO price_history(product_key,price,campaign,recorded_at) VALUES(?,?,?,?)",
                (product_key, price, campaign, datetime.now().isoformat(timespec="seconds")),
            )

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        data = dict(row)
        try:
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        except Exception:
            data["metadata"] = {}
        return data
