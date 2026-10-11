"""Temporary Qt5 compatibility adapter; business workflow is in services.

Remove with the old score page at P6. This is deliberately under app, not
under the Qt-free API: it accepts the legacy account/session abstractions.
"""

from contextlib import nullcontext

from auth import ServerError
from gmis.score import GraduateScore
from jwxt.schedule import Schedule
from jwxt.score import Score
from xjtutoolbox.contracts.data import AccountInfo, AppError, Cancelled, ScoreRequest
from xjtutoolbox.runtime import TaskRegistry, TaskState
from xjtutoolbox.services import AcademicService

from .account import request_mfa


class _LegacyError(AppError):
    def __init__(self, error):
        super().__init__(getattr(error, "message", str(error)))
        self.code = (
            "legacy_mfa"
            if isinstance(error, ServerError) and error.code == 102
            else "legacy_error"
        )


class LegacyAcademicAPI:
    def __init__(self, account, postgraduate, allow_qrcode_login=True):
        self._account = account
        self._postgraduate = postgraduate
        self._allow_qrcode_login = allow_qrcode_login
        self._id = getattr(account, "uuid", str(id(account)))
        self._session = None

    def account_scope(self, account_id):
        return nullcontext()

    def account(self, account_id):
        return AccountInfo(
            self._id,
            self._account.username,
            self._account.username,
            "postgraduate" if self._postgraduate else "undergraduate",
        )

    def authenticate(self, account_id, site, answer=None):
        self._session = self._account.session_manager.get_session(site)
        try:
            self._session.ensure_login(
                self._account.username,
                self._account.password,
                account=self._account,
                mfa_provider=self._account.session_manager.mfa_provider,
                allow_qrcode_login=self._allow_qrcode_login,
            )
        except Exception as exc:
            raise _LegacyError(exc) from exc

    def current_term(self, account_id):
        return Schedule(self._session).termString

    def scores(self, account_id, terms):
        if self._postgraduate:
            return GraduateScore(self._session).grade()
        return Score(self._session).grade(
            list(terms) if terms else None, jwapp_format=True
        )

    def reported_scores(self, account_id, terms):
        return Score(self._session).reported_grade(
            student_id=self._account.username, term=list(terms) if terms else None
        )

    def assert_valid(self, account_id):
        pass


def run_legacy_scores(thread, account, postgraduate, terms=None, include_report=False):
    if account is None:
        thread.error.emit("未登录", "请先添加一个账户")
        thread.canceled.emit()
        return
    api = LegacyAcademicAPI(account, postgraduate, thread.allow_qrcode_login)
    request = ScoreRequest(
        api._id, tuple(terms) if terms else None, terms == [], include_report
    )
    registry = TaskRegistry()
    task_id = registry.register(api._id)

    class Context:
        def __init__(self, context):
            self.context = context

        def check_cancelled(self):
            if not thread.can_run:
                raise Cancelled()
            self.context.check_cancelled()

        def report(self, progress):
            self.context.report(progress)
            thread.setIndeterminate.emit(progress.overall is None)
            thread.messageChanged.emit(progress.message)

    service = AcademicService(api)
    task = registry.run(
        task_id, lambda context: service.query_scores(request, Context(context))
    )
    if task.state == TaskState.SUCCEEDED:
        thread.setIndeterminate.emit(False)
        thread.progressChanged.emit(100)
        thread.scores.emit(list(task.result.rows), task.result.postgraduate)
        thread.hasFinished.emit()
    else:
        if task.error:
            title = "登录问题" if task.error.code == "legacy_mfa" else "查询失败"
            thread.error.emit(title, task.error.message)
            if task.error.code == "legacy_mfa":
                request_mfa(account)
        thread.canceled.emit()
