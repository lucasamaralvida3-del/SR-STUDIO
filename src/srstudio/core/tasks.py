from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class TaskCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class TaskProgress:
    current: int = 0
    total: int = 0
    message: str = ""

    @property
    def percent(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(100.0, self.current * 100.0 / self.total))


class TaskContext:
    def __init__(self, cancel_event: threading.Event, progress_queue: queue.Queue[TaskProgress]) -> None:
        self._cancel_event = cancel_event
        self._progress_queue = progress_queue

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def checkpoint(self) -> None:
        if self.cancelled:
            raise TaskCancelled("Operação cancelada")

    def progress(self, current: int, total: int, message: str = "") -> None:
        self.checkpoint()
        self._progress_queue.put(TaskProgress(current, total, message))


class BackgroundTask(Generic[T]):
    """Runner simples para importação/exportação sem bloquear a UI Tk."""

    def __init__(self, target: Callable[[TaskContext], T]) -> None:
        self._target = target
        self._cancel = threading.Event()
        self.progress_queue: queue.Queue[TaskProgress] = queue.Queue()
        self.result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None

    def start(self) -> "BackgroundTask[T]":
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Tarefa já está em execução")
        self._thread = threading.Thread(target=self._run, name="SRStudioTask", daemon=True)
        self._thread.start()
        return self

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self) -> None:
        context = TaskContext(self._cancel, self.progress_queue)
        try:
            self.result_queue.put((True, self._target(context)))
        except Exception as exc:
            self.result_queue.put((False, exc))

    def done(self) -> bool:
        return bool(self._thread and not self._thread.is_alive())
