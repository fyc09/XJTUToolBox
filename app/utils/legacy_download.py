"""Temporary adapter for the Qt5 attachment downloader; no workflow copy."""

from contextlib import nullcontext

from xjtutoolbox.contracts.data import Cancelled, DownloadRequest
from xjtutoolbox.infrastructure.http import DownloadStream
from xjtutoolbox.infrastructure.storage import DownloadFile
from xjtutoolbox.runtime import TaskRegistry, TaskState
from xjtutoolbox.services import DownloadService


class LegacyDownloadAPI:
    def __init__(self, session):
        self._session = session

    def account_scope(self, account_id):
        return nullcontext()

    def authenticate(self, account_id, site, answer=None):
        # The old LMS page already owns an authenticated, captured session.
        pass

    def assert_valid(self, account_id):
        pass

    def open_download(self, account_id, url):
        response = self._session.get(
            url, stream=True, timeout=(10, 30), headers={"Accept-Encoding": "identity"}
        )
        try:
            response.raise_for_status()
            return DownloadStream(response)
        except Exception:
            response.close()
            raise

    def prepare_download(self, account_id, destination):
        return DownloadFile(destination, lambda action: action())


def run_legacy_download(thread):
    registry = TaskRegistry()
    task_id = registry.register()

    class Context:
        def __init__(self, context):
            self.context = context

        def check_cancelled(self):
            if not thread.can_run:
                raise Cancelled()
            self.context.check_cancelled()

        def report(self, progress):
            self.context.report(progress)
            thread.titleChanged.emit("正在下载附件")
            thread.messageChanged.emit(progress.message)
            thread.progressPaused.emit(progress.total is None)
            if progress.total and progress.completed is not None:
                thread.progressChanged.emit(
                    min(100, int(progress.completed * 100 / progress.total))
                )

    request = DownloadRequest("legacy-session", thread.url, thread.output_path)
    service = DownloadService(LegacyDownloadAPI(thread.session))
    task = registry.run(
        task_id, lambda context: service.download(request, Context(context))
    )
    if task.state == TaskState.SUCCEEDED:
        thread.progressPaused.emit(False)
        thread.progressChanged.emit(100)
        thread.messageChanged.emit("下载完成")
        thread.hasFinished.emit()
    else:
        if task.error:
            thread.error.emit("下载失败", task.error.message)
        thread.canceled.emit()
