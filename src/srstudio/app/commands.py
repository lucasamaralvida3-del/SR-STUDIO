from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass(frozen=True, slots=True)
class StudioCommand:
    id: str
    title: str
    category: str
    shortcut: str = ""
    keywords: tuple[str, ...] = ()
    handler: Callable[[], object] | None = field(default=None, compare=False, repr=False)


class CommandRegistry:
    """Registro central para Command Palette, menus e atalhos."""

    def __init__(self) -> None:
        self._commands: dict[str, StudioCommand] = {}

    def register(self, command: StudioCommand) -> None:
        self._commands[command.id] = command

    def unregister(self, command_id: str) -> None:
        self._commands.pop(command_id, None)

    def get(self, command_id: str) -> StudioCommand | None:
        return self._commands.get(command_id)

    def all(self) -> list[StudioCommand]:
        return sorted(self._commands.values(), key=lambda item: (item.category.lower(), item.title.lower()))

    def search(self, text: str, limit: int = 20) -> list[StudioCommand]:
        query = " ".join(str(text or "").strip().lower().split())
        if not query:
            return self.all()[:limit]
        scored: list[tuple[int, StudioCommand]] = []
        for command in self._commands.values():
            haystack = " ".join((command.title, command.category, command.shortcut, *command.keywords)).lower()
            if query == command.id.lower():
                score = 100
            elif query in command.title.lower():
                score = 80
            elif query in haystack:
                score = 60
            else:
                tokens = [token for token in query.split() if token]
                matches = sum(token in haystack for token in tokens)
                if not matches:
                    continue
                score = 20 + matches * 10
            scored.append((score, command))
        scored.sort(key=lambda item: (-item[0], item[1].title.lower()))
        return [command for _, command in scored[:limit]]

    def execute(self, command_id: str) -> object | None:
        command = self._commands.get(command_id)
        if command is None:
            raise KeyError(command_id)
        if command.handler is None:
            return None
        return command.handler()

    def extend(self, commands: Iterable[StudioCommand]) -> None:
        for command in commands:
            self.register(command)
