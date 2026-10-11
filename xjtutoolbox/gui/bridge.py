from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Qt, Signal, Slot

from xjtutoolbox.runtime import TaskRegistry


class ExecutionBridge(QObject):
    changed = Signal(object)
    _wake = Signal()

    def __init__(self, tasks: TaskRegistry, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self._pool = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="xjtu-service"
        )
        self._lock = threading.Lock()
        self._futures = set()
        self._pending = {}
        self._wake_pending = False
        self._wake.connect(self._drain, Qt.ConnectionType.QueuedConnection)
        self._unsubscribe = tasks.subscribe(self._queue)

    def _queue(self, snapshot):
        with self._lock:
            self._pending[snapshot.task_id] = snapshot
            wake = not self._wake_pending
            self._wake_pending = True
        if wake:
            self._wake.emit()

    @Slot()
    def _drain(self):
        with self._lock:
            ids = tuple(self._pending)
            self._pending.clear()
            self._wake_pending = False
        for task_id in ids:
            self.changed.emit(self.tasks.snapshot(task_id))

    def submit(self, task_id, operation):
        future = self._pool.submit(self.tasks.run, task_id, operation)
        with self._lock:
            self._futures.add(future)
        future.add_done_callback(self._finished)

    def _finished(self, future):
        with self._lock:
            self._futures.discard(future)

    def idle(self):
        with self._lock:
            return not self._futures

    def begin_shutdown(self):
        self.tasks.begin_shutdown()

    def close(self):
        self.tasks.begin_shutdown()
        self._pool.shutdown(wait=True, cancel_futures=True)
        self._unsubscribe()
