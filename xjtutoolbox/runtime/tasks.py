from __future__ import annotations

import copy
import logging
import threading
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from xjtutoolbox.contracts.data import Cancelled, ErrorInfo
from xjtutoolbox.contracts.tasks import Progress, RunContext


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    account_id: str | None
    state: TaskState = TaskState.PENDING
    progress: Progress | None = None
    cancel_requested: bool = False
    result: Any = None
    error: ErrorInfo | None = None


class _Context:
    def __init__(self, registry: TaskRegistry, task_id: str):
        self.registry, self.task_id = registry, task_id

    def check_cancelled(self) -> None:
        if self.registry.snapshot(self.task_id).cancel_requested:
            raise Cancelled()

    def report(self, progress: Progress) -> None:
        self.registry._progress(self.task_id, progress)


class TaskRegistry:
    """Own task lifetimes; execution is supplied by a frontend adapter.

    The registry never starts threads, touches Qt, or infers success from
    progress. A cancellation request is not completion of running work.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._tasks: dict[str, TaskSnapshot] = {}
        self._listeners: dict[str, Callable[[TaskSnapshot], None]] = {}
        self._accepting = True

    def register(self, account_id: str | None = None) -> str:
        with self._lock:
            if not self._accepting:
                raise RuntimeError("task runtime is shutting down")
            task_id = str(uuid4())
            self._tasks[task_id] = TaskSnapshot(task_id, account_id)
        self._notify(task_id)
        return task_id

    def snapshot(self, task_id: str) -> TaskSnapshot:
        with self._lock:
            return copy.deepcopy(self._tasks[task_id])

    def subscribe(self, listener: Callable[[TaskSnapshot], None]) -> Callable[[], None]:
        listener_id = str(uuid4())
        with self._lock:
            self._listeners[listener_id] = listener

        def unsubscribe() -> None:
            with self._lock:
                self._listeners.pop(listener_id, None)

        return unsubscribe

    def _notify(self, task_id: str) -> None:
        with self._lock:
            snapshot = copy.deepcopy(self._tasks[task_id])
            listeners = tuple(self._listeners.values())
        for listener in listeners:
            try:
                listener(copy.deepcopy(snapshot))
            except BaseException:
                logging.getLogger(__name__).error("Task subscriber failed")

    def cancel(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            if task.state in TERMINAL:
                return
            state = (
                TaskState.CANCELLED if task.state == TaskState.PENDING else task.state
            )
            self._tasks[task_id] = replace(task, cancel_requested=True, state=state)
        self._notify(task_id)

    def cancel_account(self, account_id: str) -> None:
        with self._lock:
            ids = [
                t.task_id for t in self._tasks.values() if t.account_id == account_id
            ]
        for task_id in ids:
            self.cancel(task_id)

    def begin_shutdown(self) -> None:
        with self._lock:
            self._accepting = False
            ids = tuple(self._tasks)
        for task_id in ids:
            self.cancel(task_id)

    def active(self) -> tuple[TaskSnapshot, ...]:
        with self._lock:
            return tuple(
                copy.deepcopy(t)
                for t in self._tasks.values()
                if t.state not in TERMINAL
            )

    def _progress(self, task_id: str, progress: Progress) -> None:
        with self._lock:
            task = self._tasks[task_id]
            if task.state != TaskState.RUNNING:
                return
            self._tasks[task_id] = replace(task, progress=progress)
        self._notify(task_id)

    def run(self, task_id: str, operation: Callable[[RunContext], Any]) -> TaskSnapshot:
        with self._lock:
            task = self._tasks[task_id]
            if task.state != TaskState.PENDING:
                return self.snapshot(task_id)
            self._tasks[task_id] = replace(task, state=TaskState.RUNNING)
        self._notify(task_id)
        result, error = None, None
        try:
            context = _Context(self, task_id)
            context.check_cancelled()
            result = operation(context)
            state = TaskState.SUCCEEDED
        except Cancelled as exc:
            state, result = TaskState.CANCELLED, exc.partial_result
        except KeyboardInterrupt:
            state = TaskState.CANCELLED
        except BaseException as exc:
            state, error = TaskState.FAILED, ErrorInfo.from_exception(exc)
            logging.getLogger(__name__).debug(
                "Task failure type: %s", type(exc).__name__
            )
        with self._lock:
            task = self._tasks[task_id]
            self._tasks[task_id] = replace(
                task, state=state, result=result, error=error
            )
        self._notify(task_id)
        return self.snapshot(task_id)
