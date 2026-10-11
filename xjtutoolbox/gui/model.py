from __future__ import annotations

from dataclasses import asdict, replace

from PySide6.QtCore import QObject, Property, QThread, QTimer, Qt, Signal, Slot

from xjtutoolbox.contracts.data import (
    AppError,
    ChallengeAnswer,
    DownloadRequest,
    ScoreRequest,
)
from xjtutoolbox.runtime import TaskState


class ViewModel(QObject):
    changed = Signal()
    paletteChanged = Signal()
    quitReady = Signal()

    def __init__(self, accounts, academic, downloads, bridge, parent=None):
        super().__init__(parent)
        self._accounts, self._academic, self._downloads, self._bridge = (
            accounts,
            academic,
            downloads,
            bridge,
        )
        self._account_id = ""
        self._rows, self._challenge = [], {}
        self._task_id, self._request, self._operation = "", None, None
        self._busy, self._closing = False, False
        self._status, self._message = "", ""
        self._progress = -1.0
        self._dark = accounts.color_mode() == "dark"
        bridge.changed.connect(self._accept, Qt.ConnectionType.QueuedConnection)
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(50)
        self._shutdown_timer.timeout.connect(self._finish_shutdown)
        self._refresh_accounts()

    def _refresh_accounts(self):
        self._account_rows = [asdict(a) for a in self._accounts.list_accounts()]
        if self._account_id not in {a["account_id"] for a in self._account_rows}:
            self.selectAccount(
                self._account_rows[0]["account_id"] if self._account_rows else ""
            )
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def accounts(self):
        return self._account_rows

    @Property(str, notify=changed)
    def accountId(self):
        return self._account_id

    @Property("QVariantList", notify=changed)
    def rows(self):
        return self._rows

    @Property("QVariantMap", notify=changed)
    def challenge(self):
        return self._challenge

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def canClose(self):
        return self._closing and self._bridge.idle()

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(float, notify=changed)
    def progress(self):
        return self._progress

    @Property(bool, notify=paletteChanged)
    def dark(self):
        return self._dark

    @Property("QVariantMap", notify=paletteChanged)
    def palette(self):
        if self._dark:
            return {
                "window": "#252525",
                "windowText": "#eeeeee",
                "base": "#191919",
                "alternateBase": "#303030",
                "text": "#eeeeee",
                "button": "#353535",
                "buttonText": "#eeeeee",
                "toolTipBase": "#353535",
                "toolTipText": "#eeeeee",
                "placeholderText": "#b0b0b0",
                "disabledText": "#888888",
            }
        return {
            "window": "#f4f4f4",
            "windowText": "#202020",
            "base": "#ffffff",
            "alternateBase": "#eeeeee",
            "text": "#202020",
            "button": "#e0e0e0",
            "buttonText": "#202020",
            "toolTipBase": "#ffffff",
            "toolTipText": "#202020",
            "placeholderText": "#666666",
            "disabledText": "#888888",
        }

    @Slot(bool)
    def setDark(self, value):
        try:
            self._accounts.set_color_mode("dark" if value else "light")
            self._dark = value
            self.paletteChanged.emit()
        except AppError as exc:
            self._message = str(exc)
            self.changed.emit()

    @Slot(str)
    def selectAccount(self, account_id):
        if self._account_id == account_id:
            return
        self.cancel()
        self._account_id, self._task_id = account_id, ""
        self._rows, self._challenge = [], {}
        self._request, self._operation = None, None
        self._busy, self._progress, self._status, self._message = False, -1, "", ""
        self.changed.emit()

    @Slot(str, str, str, str, bool)
    def addAccount(self, username, password, nickname, kind, remember):
        try:
            account = self._accounts.add(username, password, nickname, kind, remember)
            self._refresh_accounts()
            self.selectAccount(account.account_id)
        except AppError as exc:
            self._message = str(exc)
            self.changed.emit()

    @Slot(str)
    def unlock(self, password):
        try:
            self._accounts.unlock(self._account_id, password)
            self._message = "已为本次运行设置密码"
        except AppError as exc:
            self._message = str(exc)
        self.changed.emit()

    @Slot()
    def removeAccount(self):
        try:
            self._accounts.remove(self._account_id)
            self.selectAccount("")
            self._refresh_accounts()
        except AppError as exc:
            self._message = str(exc)
            self.changed.emit()

    def _start(self, request, operation):
        if self._closing or not request.account_id:
            self._message = "请先添加并选择账户"
            self.changed.emit()
            return
        self.cancel()
        self._request, self._operation = request, operation
        self._task_id = self._bridge.tasks.register(request.account_id)
        self._busy, self._status, self._message, self._progress = (
            True,
            "等待执行",
            "",
            -1,
        )
        self._challenge = {}
        self.changed.emit()
        self._bridge.submit(self._task_id, lambda context: operation(request, context))

    @Slot(str, bool, bool)
    def queryScores(self, terms, current_term, include_report):
        self._rows = []
        request = ScoreRequest(
            self._account_id,
            tuple(t.strip() for t in terms.split(",") if t.strip()) or None,
            current_term,
            include_report,
        )
        self._start(request, self._academic.query_scores)

    @Slot(str, str)
    def download(self, url, destination):
        self._start(
            DownloadRequest(self._account_id, url, destination),
            self._downloads.download,
        )

    @Slot(str)
    def answerChallenge(self, value):
        if (
            self._challenge
            and self._request
            and self._challenge["account_id"] == self._account_id
        ):
            request = replace(
                self._request,
                answer=ChallengeAnswer(self._challenge["challenge_id"], value),
            )
            self._start(request, self._operation)

    @Slot()
    def cancel(self):
        if self._task_id:
            self._bridge.tasks.cancel(self._task_id)

    @Slot(object)
    def _accept(self, event):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("presentation model updated outside its Qt thread")
        if event.task_id != self._task_id or event.account_id != self._account_id:
            return
        # Read current state, since already queued events may arrive out of order.
        task = self._bridge.tasks.snapshot(event.task_id)
        self._busy = task.state in (TaskState.PENDING, TaskState.RUNNING)
        self._status = {
            TaskState.PENDING: "等待执行",
            TaskState.RUNNING: "正在执行",
            TaskState.SUCCEEDED: "已完成",
            TaskState.FAILED: "操作失败",
            TaskState.CANCELLED: "已取消",
        }[task.state]
        if self._busy and task.cancel_requested:
            self._status = "正在取消"
        if task.progress:
            progress = task.progress
            self._message = progress.message
            self._progress = progress.overall if progress.overall is not None else -1
            if progress.completed is not None:
                self._message += (
                    f" {progress.completed}/{progress.total or '?'} {progress.unit}"
                )
                if progress.total:
                    self._progress = min(100, progress.completed * 100 / progress.total)
        if task.state == TaskState.SUCCEEDED:
            self._progress = 100
            if hasattr(task.result, "rows"):
                self._rows = list(task.result.rows)
                self._message = f"共 {len(self._rows)} 条成绩"
            elif hasattr(task.result, "path"):
                self._message = task.result.path
        elif task.error:
            self._message = task.error.message
            self._challenge = (
                asdict(task.error.challenge) if task.error.challenge else {}
            )
        self.changed.emit()

    @Slot()
    def requestClose(self):
        if self._closing:
            return
        self._closing = True
        self._bridge.begin_shutdown()
        self._status = "正在取消任务并退出"
        self.changed.emit()
        self._shutdown_timer.start()
        self._finish_shutdown()

    def _finish_shutdown(self):
        if self._bridge.idle():
            self._shutdown_timer.stop()
            self.changed.emit()
            self.quitReady.emit()
