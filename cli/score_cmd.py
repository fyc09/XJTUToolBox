"""
成绩查询 CLI 命令
"""

from cli.output import print_error, print_paginated
from cli.session import get_account_manager, require_current_account, get_logged_in_session
from shared.account import Account
from auth.constant import JWXT_LOGIN_URL


def cmd_query(semester: str = None, page: int = 1, page_size: int = 10,
              use_webvpn: bool = False, use_json: bool = False):
    """查询成绩。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=use_webvpn)

        extra = {
            "username": account.username,
            "account_type": "本科生" if account.type == Account.AccountType.UNDERGRADUATE else "研究生",
            "semester": semester or "全部学期",
        }

        if account.type == Account.AccountType.UNDERGRADUATE:
            from jwxt.score import Score
            score_api = Score(session)

            terms = [semester] if semester else None
            scores = score_api.grade(terms)

            if not isinstance(scores, list):
                scores = []

            # 统计信息
            if scores:
                total_credits = sum(float(s.get("coursePoint", 0) or 0) for s in scores)
                total_gpa_points = sum(float(s.get("gpa", 0) or 0) * float(s.get("coursePoint", 0) or 0) for s in scores if s.get("gpa"))
                avg_gpa = round(total_gpa_points / total_credits, 2) if total_credits > 0 else 0
                extra["statistics"] = {
                    "total_credits": round(total_credits, 1),
                    "avg_gpa": avg_gpa,
                }

            print_paginated(scores, page, page_size, use_json,
                            title="成绩查询结果",
                            key="scores",
                            extra=extra)
        else:
            from gmis.score import GraduateScore
            scores = GraduateScore(session).grade()
            if not isinstance(scores, list):
                scores = []
            print_paginated(scores, page, page_size, use_json,
                            title="成绩查询结果",
                            key="scores",
                            extra=extra)

    except Exception as e:
        print_error(f"查询成绩失败: {e}", use_json)
