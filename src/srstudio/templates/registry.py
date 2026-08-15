from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TemplateDefinition:
    id: str
    name: str
    version: int = 1
    category: str = "Geral"
    page_width: float = 1080.0
    page_height: float = 1350.0
    background: str = "#FFFFFF"
    card_style: str = "product-card-default"
    layout: str = "auto"
    master_elements: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)


class TemplateRegistry:
    """Biblioteca de templates SR com persistência simples e versionada."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path.home() / ".srstudio5" / "templates"
        self.root.mkdir(parents=True, exist_ok=True)
        self.seed_defaults()

    def save(self, template: TemplateDefinition) -> Path:
        path = self.root / f"{template.id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(template), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, template_id: str) -> TemplateDefinition:
        path = self.root / f"{template_id}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TemplateDefinition(**raw)

    def list(self, category: str | None = None) -> list[TemplateDefinition]:
        templates: list[TemplateDefinition] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                item = TemplateDefinition(**json.loads(path.read_text(encoding="utf-8")))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if category and item.category.casefold() != category.casefold():
                continue
            templates.append(item)
        return templates

    def all(self) -> tuple[TemplateDefinition, ...]:
        return tuple(self.list())

    def duplicate(self, template_id: str, new_id: str, new_name: str) -> TemplateDefinition:
        original = self.load(template_id)
        clone = TemplateDefinition(
            id=new_id,
            name=new_name,
            version=1,
            category=original.category,
            page_width=original.page_width,
            page_height=original.page_height,
            background=original.background,
            card_style=original.card_style,
            layout=original.layout,
            master_elements=[dict(item) for item in original.master_elements],
            settings=dict(original.settings),
        )
        self.save(clone)
        return clone

    def seed_defaults(self) -> list[TemplateDefinition]:
        defaults = [
            TemplateDefinition("terca-verde", "Terça Verde", category="Hortifruti", layout="grid"),
            TemplateDefinition("quarta-cafe", "Quarta Café", category="Padaria", layout="hero"),
            TemplateDefinition("quinta-file", "Quinta Filé", category="Açougue", layout="hero"),
            TemplateDefinition("segunda-limpeza", "Segunda da Limpeza", category="Limpeza", layout="grid"),
            TemplateDefinition("fim-semana", "Fim de Semana", category="Geral", layout="auto"),
            TemplateDefinition("atacado", "Atacado", category="Atacado", layout="grid", settings={"two_prices": True}),
        ]
        for item in defaults:
            path = self.root / f"{item.id}.json"
            if not path.exists():
                self.save(item)
        return defaults
