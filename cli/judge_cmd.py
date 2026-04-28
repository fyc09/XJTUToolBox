"""
评教 CLI 命令（本科生 + 研究生）

注意：这是一键评教的核心模块，必须使用正确的 API 方法名。
"""

from cli.output import print_output, print_error, print_success
from cli.session import get_account_manager, require_current_account, get_logged_in_session
from shared.account import Account
from auth.constant import JWXT_LOGIN_URL


def cmd_list(show_completed: bool = False, use_webvpn: bool = False, use_json: bool = False):
    """列出评教问卷。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        if account.type == Account.AccountType.UNDERGRADUATE:
            _list_undergraduate(account, show_completed, use_webvpn, use_json)
        else:
            _list_postgraduate(account, show_completed, use_webvpn, use_json)
    except Exception as e:
        print_error(f"获取评教问卷失败: {e}", use_json)


def _list_undergraduate(account, show_completed, use_webvpn, use_json):
    from jwxt.judge import AutoJudge

    session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=use_webvpn)
    judge = AutoJudge(session)

    if show_completed:
        questionnaires = judge.allQuestionnaires()
    else:
        questionnaires = judge.unfinishedQuestionnaires()

    result = []
    for q in (questionnaires or []):
        result.append({
            "course": q.KCM,
            "teacher": q.BPR,
            "type": "过程性" if q.PGLXDM == "05" else "期末",
            "wjdm": q.WJDM,
            "jxb_id": q.JXBID,
        })

    print_output({"questionnaires": result, "count": len(result)}, use_json, title="评教问卷列表")


def _list_postgraduate(account, show_completed, use_webvpn, use_json):
    from gste.judge import GraduateAutoJudge

    session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=True)
    gj = GraduateAutoJudge(session, use_webvpn=True)
    questionnaires = gj.getQuestionnaires()

    result = []
    for q in (questionnaires or []):
        is_completed = getattr(q, "is_completed", False)
        if not show_completed and is_completed:
            continue
        result.append({
            "course": getattr(q, "course_name", str(q)),
            "status": "已完成" if is_completed else "未完成",
        })

    print_output({"questionnaires": result, "count": len(result)}, use_json, title="研究生评教问卷列表")


def cmd_all(score: str = "95", comment: str = "老师讲得很好，课程内容充实。", use_webvpn: bool = False, use_json: bool = False):
    """一键全部评教。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        if account.type == Account.AccountType.UNDERGRADUATE:
            _all_undergraduate(account, score, comment, use_webvpn, use_json)
        else:
            _all_postgraduate(account, score, comment, use_webvpn, use_json)
    except Exception as e:
        print_error(f"评教失败: {e}", use_json)


def _all_undergraduate(account, score_str, comment, use_webvpn, use_json):
    from jwxt.judge import AutoJudge

    session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=use_webvpn)
    judge = AutoJudge(session)

    # 获取未完成的问卷
    questionnaires = judge.unfinishedQuestionnaires()

    if not questionnaires:
        print_error("没有未完成的评教问卷。", use_json)
        return

    username = account.username
    success_count = 0
    fail_count = 0

    for q in questionnaires:
        try:
            # 获取问卷题目数据
            data_list = judge.questionnaireData(q, username)

            # 自动填写：分值题填高分，客观题填第一个选项，文本题填评语
            for item in data_list:
                max_score = item.getMaxScore()
                if max_score > 0:
                    # 分值题：填最高分
                    item.setScore(max_score)
                elif item.DADM:
                    # 客观题：填第一个选项
                    item.setOption(item.DADM)
                elif item.SFBT == "1":
                    # 文本题：填评语
                    item.setSubjectiveOption(comment)

            # 提交
            ok, msg = judge.submitQuestionnaire(q, data_list)
            if ok:
                success_count += 1
            else:
                fail_count += 1
        except Exception:
            fail_count += 1

    print_success(f"评教完成: {success_count} 成功, {fail_count} 失败",
                  {"total": len(questionnaires), "success": success_count, "fail": fail_count},
                  use_json)


def _all_postgraduate(account, score_str, comment, use_webvpn, use_json):
    from gste.judge import GraduateAutoJudge

    session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=True)
    gj = GraduateAutoJudge(session, use_webvpn=True)
    questionnaires = gj.getQuestionnaires()

    if not questionnaires:
        print_error("没有可评教的问卷。", use_json)
        return

    success_count = 0
    fail_count = 0
    for q in questionnaires:
        try:
            questionnaire_data = gj.getQuestionnaireData(q)
            # 自动填写（使用 autofill 方法）
            questionnaire_data.autofill(default_text=comment)
            questionnaire_data.set_all_textarea(comment)
            gj.submitQuestionnaire(q, questionnaire_data)
            success_count += 1
        except Exception:
            fail_count += 1

    print_success(f"评教完成: {success_count} 成功, {fail_count} 失败",
                  {"success": success_count, "fail": fail_count},
                  use_json)
