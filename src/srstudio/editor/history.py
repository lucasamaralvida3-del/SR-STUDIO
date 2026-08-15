from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class Command(Protocol):
    label: str

    def do(self) -> None: ...
    def undo(self) -> None: ...


@dataclass(slots=True)
class LambdaCommand:
    label: str
    _do: Callable[[], None]
    _undo: Callable[[], None]

    def do(self) -> None:
        self._do()

    def undo(self) -> None:
        self._undo()


class CommandHistory:
    """Undo/redo transacional para ações do editor e da SR IA."""

    def __init__(self, limit: int = 300) -> None:
        self.limit = max(20, int(limit))
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._transaction: list[Command] | None = None
        self._transaction_label = ""

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def execute(self, command: Command) -> None:
        command.do()
        if self._transaction is not None:
            self._transaction.append(command)
            return
        self._push(command)

    def _push(self, command: Command) -> None:
        self._undo.append(command)
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()

    def begin(self, label: str) -> None:
        if self._transaction is not None:
            raise RuntimeError("Já existe uma transação de histórico ativa")
        self._transaction = []
        self._transaction_label = label

    def commit(self) -> None:
        commands = self._transaction
        label = self._transaction_label
        self._transaction = None
        self._transaction_label = ""
        if not commands:
            return

        def redo_all() -> None:
            for item in commands:
                item.do()

        def undo_all() -> None:
            for item in reversed(commands):
                item.undo()

        self._push(LambdaCommand(label=label, _do=redo_all, _undo=undo_all))

    def rollback(self) -> None:
        commands = self._transaction or []
        for item in reversed(commands):
            item.undo()
        self._transaction = None
        self._transaction_label = ""

    def undo(self) -> str:
        if not self._undo:
            return ""
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)
        return command.label

    def redo(self) -> str:
        if not self._redo:
            return ""
        command = self._redo.pop()
        command.do()
        self._undo.append(command)
        return command.label

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._transaction = None
        self._transaction_label = ""
