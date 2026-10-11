from __future__ import annotations

from xjtutoolbox.api import CampusAPI
from xjtutoolbox.contracts.data import (
    AppError,
    DownloadRequest,
    DownloadResult,
    ProtocolError,
)
from xjtutoolbox.contracts.tasks import Progress, RunContext


class DownloadService:
    def __init__(self, api: CampusAPI):
        self._api = api

    def download(self, request: DownloadRequest, context: RunContext) -> DownloadResult:
        if not request.destination.strip():
            raise AppError("请选择下载目标文件")
        context.check_cancelled()
        with self._api.account_scope(request.account_id):
            context.check_cancelled()
            context.report(Progress("authenticate", "正在认证思源学堂"))
            self._api.authenticate(request.account_id, "lms", request.answer)
            context.check_cancelled()
            with self._api.open_download(request.account_id, request.url) as stream:
                with self._api.prepare_download(
                    request.account_id, request.destination
                ) as output:
                    completed = 0
                    context.report(
                        Progress("download", "正在下载", 0, stream.length, "bytes")
                    )
                    for chunk in stream.chunks():
                        context.check_cancelled()
                        self._api.assert_valid(request.account_id)
                        if chunk:
                            output.write(chunk)
                            completed += len(chunk)
                            context.report(
                                Progress(
                                    "download",
                                    "正在下载",
                                    completed,
                                    stream.length,
                                    "bytes",
                                )
                            )
                    if stream.length is not None and completed != stream.length:
                        raise ProtocolError("下载长度不完整，原目标文件已保留")
                    context.check_cancelled()
                    path = output.commit()
            # A late cancellation cannot undo an already committed file.
            return DownloadResult(request.account_id, path, completed)
