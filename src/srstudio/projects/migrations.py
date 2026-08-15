from __future__ import annotations

from copy import deepcopy
from typing import Callable

CURRENT_SCHEMA = 2
Migration = Callable[[dict], dict]


def _v1_to_v2(data: dict) -> dict:
    result = deepcopy(data)
    result.setdefault("metadata", {})
    result["metadata"].setdefault("migrated_from", 1)
    for page in result.get("pages", []):
        page.setdefault("master_page", False)
        page.setdefault("safe_area", {"enabled": True, "margin_mm": 5.0})
        for element in page.get("elements", []):
            element.setdefault("locked", False)
            element.setdefault("visible", True)
            element.setdefault("style_id", "")
    result["schema_version"] = 2
    return result


MIGRATIONS: dict[int, Migration] = {
    1: _v1_to_v2,
}


def migrate_project(data: dict) -> dict:
    current = int(data.get("schema_version") or 1)
    if current > CURRENT_SCHEMA:
        raise ValueError(f"Projeto foi criado por uma versão mais nova do SR Studio (schema {current}).")
    result = deepcopy(data)
    while current < CURRENT_SCHEMA:
        migration = MIGRATIONS.get(current)
        if migration is None:
            raise ValueError(f"Migração não disponível para schema {current}.")
        result = migration(result)
        current = int(result.get("schema_version") or current + 1)
    return result
