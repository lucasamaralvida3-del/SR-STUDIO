from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from srstudio.core.models import Page, Product, ProductCard, StudioProject


CURRENT_SCHEMA = 1


class ProjectStore:
    def __init__(self, autosave_dir: str | Path) -> None:
        self.autosave_dir = Path(autosave_dir)
        self.autosave_dir.mkdir(parents=True, exist_ok=True)

    def save(self, project: StudioProject, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = project.to_dict()
        payload["schema_version"] = CURRENT_SCHEMA
        with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=target.parent, suffix=".tmp") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)
        temp_path.replace(target)
        return target

    def autosave(self, project: StudioProject) -> Path:
        return self.save(project, self.autosave_dir / f"{project.id}.autosave.srproject")

    def load(self, path: str | Path) -> StudioProject:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        payload = self._migrate(payload)
        products = [Product.from_dict(item) for item in payload.get("products", [])]
        pages: list[Page] = []
        for raw_page in payload.get("pages", []):
            cards = [ProductCard(**card) for card in raw_page.get("cards", [])]
            pages.append(Page(
                id=raw_page.get("id") or "",
                name=raw_page.get("name") or "Página",
                width=float(raw_page.get("width", 1080)),
                height=float(raw_page.get("height", 1350)),
                background=raw_page.get("background", "#FFFFFF"),
                cards=cards,
                elements=list(raw_page.get("elements", [])),
            ))
        return StudioProject(
            schema_version=CURRENT_SCHEMA,
            id=payload.get("id") or "",
            name=payload.get("name") or "Projeto",
            campaign=payload.get("campaign") or "",
            products=products,
            pages=pages or [Page()],
            settings=dict(payload.get("settings", {})),
        )

    def recovery_candidates(self) -> list[Path]:
        return sorted(self.autosave_dir.glob("*.autosave.srproject"), key=lambda p: p.stat().st_mtime, reverse=True)

    def _migrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        version = int(payload.get("schema_version", 1))
        if version > CURRENT_SCHEMA:
            raise ValueError(f"Projeto criado por uma versão mais nova (schema {version}).")
        # Future migrations are applied sequentially here.
        payload["schema_version"] = CURRENT_SCHEMA
        return payload
