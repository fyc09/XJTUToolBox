from __future__ import annotations

import copy
import re

from xjtutoolbox.api import CampusAPI
from xjtutoolbox.contracts.data import AppError, ScoreRequest, ScoreResult
from xjtutoolbox.contracts.tasks import Progress, RunContext


class AcademicService:
    def __init__(self, api: CampusAPI):
        self._api = api

    def query_scores(self, request: ScoreRequest, context: RunContext) -> ScoreResult:
        if request.current_term and request.terms:
            raise AppError("当前学期与指定学期不能同时使用")
        if request.terms is not None and (
            not request.terms
            or any(
                not re.fullmatch(r"\d{4}-\d{4}-[123]", term) for term in request.terms
            )
        ):
            raise AppError("学期格式应为 YYYY-YYYY-1/2/3")
        context.check_cancelled()
        with self._api.account_scope(request.account_id):
            context.check_cancelled()
            account = self._api.account(request.account_id)
            postgraduate = account.kind == "postgraduate"
            if postgraduate and (
                request.terms or request.current_term or request.include_report
            ):
                raise AppError("研究生系统只能查询全部成绩，不支持学期筛选或本科成绩单")
            context.report(Progress("authenticate", "正在认证"))
            self._api.authenticate(
                request.account_id, "gmis" if postgraduate else "jwxt", request.answer
            )
            context.check_cancelled()
            terms = request.terms
            if request.current_term:
                context.report(Progress("term", "正在读取当前学期"))
                terms = (self._api.current_term(request.account_id),)
                context.check_cancelled()
            context.report(Progress("scores", "正在查询成绩"))
            rows = self._api.scores(request.account_id, terms)
            context.check_cancelled()
            if request.include_report:
                context.report(Progress("report", "正在查询成绩单"))
                reported = self._api.reported_scores(request.account_id, terms)
                context.check_cancelled()
                names = {row["courseName"] for row in rows}
                for row in reported:
                    if row["courseName"] not in names:
                        rows.append(row)
                        names.add(row["courseName"])
            self._api.assert_valid(request.account_id)
            return ScoreResult(
                request.account_id, postgraduate, tuple(copy.deepcopy(rows))
            )
