from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from srstudio.core.models import Product, to_decimal


@dataclass(frozen=True, slots=True)
class WholesaleChange:
    code: str
    status: str
    reason: str = ""
    alert: str = ""
    previous: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WholesaleHistorySummary:
    report_id: int
    duplicate: bool
    new: int
    changed: int
    same: int
    removed: int
    alerts: int
    removed_codes: tuple[str, ...] = ()


class WholesaleHistoryStore:
    """Persistent Atacado report memory ported from the proven Stable workflow."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else Path.home() / ".srstudio5" / "atacado-history.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reports(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_hash TEXT UNIQUE NOT NULL,
                    source_name TEXT NOT NULL,
                    report_date TEXT,
                    company_code TEXT,
                    company_name TEXT,
                    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    new_count INTEGER NOT NULL DEFAULT 0,
                    changed_count INTEGER NOT NULL DEFAULT 0,
                    same_count INTEGER NOT NULL DEFAULT 0,
                    removed_count INTEGER NOT NULL DEFAULT 0,
                    alert_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS report_items(
                    report_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    retail TEXT,
                    quantity TEXT,
                    unit TEXT,
                    wholesale TEXT,
                    total TEXT,
                    status TEXT NOT NULL,
                    reason TEXT,
                    alert TEXT,
                    previous_json TEXT,
                    PRIMARY KEY(report_id, code),
                    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
                );
                """
            )

    def analyze_and_store(
        self,
        source: str | Path,
        products: list[Product],
        metadata: dict[str, object] | None = None,
    ) -> WholesaleHistorySummary:
        source_path = Path(source)
        source_hash = self._source_hash(source_path, products)
        metadata = metadata or {}
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM reports WHERE source_hash=?",
                (source_hash,),
            ).fetchone()
            if existing:
                report_id = int(existing["id"])
                changes = self._load_changes(connection, report_id)
                self._apply_changes(products, changes)
                return self._summary(connection, report_id, duplicate=True)

            previous_id_row = connection.execute("SELECT id FROM reports ORDER BY id DESC LIMIT 1").fetchone()
            previous_id = int(previous_id_row["id"]) if previous_id_row else None
            previous = self._load_snapshot(connection, previous_id) if previous_id else {}
            changes = self.compare(products, previous)
            current_codes = {product.code for product in products if product.code}
            removed_codes = tuple(sorted(code for code in previous if code not in current_codes))
            new_count = sum(change.status == "NOVO" for change in changes.values())
            changed_count = sum(change.status == "ALTERADO" for change in changes.values())
            same_count = sum(change.status == "SEM ALTERAÇÃO" for change in changes.values())
            alert_count = sum(bool(change.alert) for change in changes.values())
            cursor = connection.execute(
                """
                INSERT INTO reports(
                    source_hash, source_name, report_date, company_code, company_name,
                    new_count, changed_count, same_count, removed_count, alert_count
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    source_hash,
                    source_path.name,
                    str(metadata.get("report_date") or ""),
                    str(metadata.get("company_code") or ""),
                    str(metadata.get("company_name") or ""),
                    new_count,
                    changed_count,
                    same_count,
                    len(removed_codes),
                    alert_count,
                ),
            )
            report_id = int(cursor.lastrowid)
            for product in products:
                if not product.code:
                    continue
                change = changes[product.code]
                snapshot = self.snapshot(product)
                connection.execute(
                    """
                    INSERT INTO report_items(
                        report_id, code, name, retail, quantity, unit, wholesale, total,
                        status, reason, alert, previous_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        report_id,
                        product.code,
                        product.name,
                        snapshot["retail"],
                        snapshot["quantity"],
                        snapshot["unit"],
                        snapshot["wholesale"],
                        snapshot["total"],
                        change.status,
                        change.reason,
                        change.alert,
                        json.dumps(change.previous, ensure_ascii=False),
                    ),
                )
            self._apply_changes(products, changes)
            return WholesaleHistorySummary(
                report_id=report_id,
                duplicate=False,
                new=new_count,
                changed=changed_count,
                same=same_count,
                removed=len(removed_codes),
                alerts=alert_count,
                removed_codes=removed_codes,
            )

    def compare(
        self,
        products: list[Product],
        previous: dict[str, dict[str, str]],
    ) -> dict[str, WholesaleChange]:
        changes: dict[str, WholesaleChange] = {}
        for product in products:
            code = product.code
            if not code:
                continue
            current = self.snapshot(product)
            old = previous.get(code)
            alert = self.alert_for(product)
            if old is None:
                changes[code] = WholesaleChange(code, "NOVO", "Produto/cartaz novo", alert)
                continue
            fields = (
                ("name", "Nome"),
                ("retail", "Varejo"),
                ("quantity", "Quantidade"),
                ("unit", "Unidade"),
                ("wholesale", "Atacado"),
            )
            changed = [label for key, label in fields if current.get(key, "") != old.get(key, "")]
            if changed:
                high_variation = self._variation_alert(current, old)
                combined = " • ".join(item for item in (alert, high_variation) if item)
                changes[code] = WholesaleChange(
                    code,
                    "ALTERADO",
                    ", ".join(changed),
                    combined,
                    previous=dict(old),
                )
            else:
                changes[code] = WholesaleChange(
                    code,
                    "SEM ALTERAÇÃO",
                    "",
                    alert,
                    previous=dict(old),
                )
        return changes

    @staticmethod
    def snapshot(product: Product) -> dict[str, str]:
        return {
            "name": WholesaleHistoryStore._norm_name(product.name),
            "retail": WholesaleHistoryStore._money(product.retail_price if product.retail_price is not None else product.price),
            "quantity": str(product.quantity or "").strip(),
            "unit": str(product.unit or "UN").strip().upper(),
            "wholesale": WholesaleHistoryStore._money(product.wholesale_price),
            "total": str(product.metadata.get("total") or ""),
        }

    @staticmethod
    def alert_for(product: Product) -> str:
        alerts: list[str] = []
        retail = to_decimal(product.retail_price if product.retail_price is not None else product.price)
        wholesale = to_decimal(product.wholesale_price)
        quantity = to_decimal(product.quantity)
        if retail is None or retail <= 0:
            alerts.append("Varejo inválido")
        if wholesale is None or wholesale <= 0:
            alerts.append("Atacado inválido")
        if quantity is None or quantity <= 0:
            alerts.append("Quantidade inválida")
        if retail is not None and wholesale is not None and wholesale >= retail:
            alerts.append("Atacado ≥ varejo")
        discount = to_decimal(product.metadata.get("discount"))
        if retail is not None and retail > 0 and wholesale is not None and discount is not None:
            calculated = (retail - wholesale) / retail * Decimal("100")
            if abs(calculated - discount) > Decimal("0.75"):
                alerts.append("Desconto divergente")
        return " • ".join(alerts)

    @staticmethod
    def _variation_alert(current: dict[str, str], old: dict[str, str]) -> str:
        alerts: list[str] = []
        for key, label in (("wholesale", "Variação alta no atacado"), ("retail", "Variação alta no varejo")):
            old_value = to_decimal(old.get(key))
            new_value = to_decimal(current.get(key))
            if old_value is not None and old_value > 0 and new_value is not None:
                if abs(new_value - old_value) / old_value > Decimal("0.30"):
                    alerts.append(label)
        return " • ".join(alerts)

    def _load_snapshot(self, connection: sqlite3.Connection, report_id: int | None) -> dict[str, dict[str, str]]:
        if report_id is None:
            return {}
        rows = connection.execute(
            "SELECT code,name,retail,quantity,unit,wholesale,total FROM report_items WHERE report_id=?",
            (report_id,),
        ).fetchall()
        return {
            row["code"]: {
                "name": self._norm_name(row["name"]),
                "retail": row["retail"] or "",
                "quantity": row["quantity"] or "",
                "unit": row["unit"] or "",
                "wholesale": row["wholesale"] or "",
                "total": row["total"] or "",
            }
            for row in rows
        }

    @staticmethod
    def _load_changes(connection: sqlite3.Connection, report_id: int) -> dict[str, WholesaleChange]:
        rows = connection.execute(
            "SELECT code,status,reason,alert,previous_json FROM report_items WHERE report_id=?",
            (report_id,),
        ).fetchall()
        result: dict[str, WholesaleChange] = {}
        for row in rows:
            try:
                previous = json.loads(row["previous_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                previous = {}
            result[row["code"]] = WholesaleChange(
                code=row["code"],
                status=row["status"],
                reason=row["reason"] or "",
                alert=row["alert"] or "",
                previous=previous,
            )
        return result

    @staticmethod
    def _apply_changes(products: list[Product], changes: dict[str, WholesaleChange]) -> None:
        for product in products:
            change = changes.get(product.code)
            if change is None:
                continue
            product.metadata["atacado_status"] = change.status
            product.metadata["atacado_reason"] = change.reason
            product.metadata["atacado_alert"] = change.alert
            product.metadata["atacado_previous"] = dict(change.previous)

    def _summary(self, connection: sqlite3.Connection, report_id: int, duplicate: bool) -> WholesaleHistorySummary:
        row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return WholesaleHistorySummary(
            report_id=report_id,
            duplicate=duplicate,
            new=int(row["new_count"]),
            changed=int(row["changed_count"]),
            same=int(row["same_count"]),
            removed=int(row["removed_count"]),
            alerts=int(row["alert_count"]),
        )

    @staticmethod
    def _source_hash(source: Path, products: list[Product]) -> str:
        digest = hashlib.sha256()
        if source.is_file():
            with source.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        payload = [WholesaleHistoryStore.snapshot(product) for product in products]
        digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _money(value) -> str:
        amount = to_decimal(value)
        if amount is None:
            return ""
        return f"{amount:.2f}".replace(".", ",")

    @staticmethod
    def _norm_name(value: str) -> str:
        return " ".join(str(value or "").upper().split())
