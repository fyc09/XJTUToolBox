"""
课表查询 CLI 命令
"""

from cli.output import print_output, print_error, print_success, print_paginated
from cli.session import get_account_manager, require_current_account, get_logged_in_session, get_logged_in_attendance_session
from shared.account import Account
from auth.constant import JWXT_LOGIN_URL
from jwxt.schedule import Schedule as JWXTSchedule
from gmis.schedule import GraduateSchedule
import datetime


def _get_schedule_data(account: Account, semester: str = None, use_webvpn: bool = False):
    """获取课表数据。"""
    session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=use_webvpn)

    if account.type == Account.AccountType.UNDERGRADUATE:
        sched = JWXTSchedule(session)
        if semester:
            schedule_data = sched.getSchedule(semester)
        else:
            schedule_data = sched.getSchedule()
        # 获取学期信息
        try:
            term = sched.termString
        except Exception:
            term = semester or "当前学期"
        return {"term": term, "schedule": schedule_data, "type": "undergraduate"}
    else:
        # 研究生课表
        gs = GraduateSchedule(session)
        schedule_data = gs.getSchedule(timestamp=semester)
        term = semester or gs.getCurrentTerm()
        return {"term": term, "schedule": schedule_data, "type": "postgraduate"}


def cmd_get(semester: str = None, week: int = None, page: int = 1, page_size: int = 10,
            use_webvpn: bool = False, use_json: bool = False):
    """获取课表。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        data = _get_schedule_data(account, semester, use_webvpn)
        lessons = data["schedule"]
        if not isinstance(lessons, list):
            lessons = []

        print_paginated(lessons, page, page_size, use_json,
                        title="课表信息",
                        key="lessons",
                        extra={
                            "term": data["term"],
                            "account_type": data["type"],
                            "username": account.username,
                            "week": week,
                        })
    except Exception as e:
        print_error(f"获取课表失败: {e}", use_json)


def cmd_exam(semester: str = None, page: int = 1, page_size: int = 10,
             use_webvpn: bool = False, use_json: bool = False):
    """获取考试安排。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=use_webvpn)

        if account.type == Account.AccountType.UNDERGRADUATE:
            sched = JWXTSchedule(session)
            exams = sched.getExamSchedule(semester)
            if not isinstance(exams, list):
                exams = []
            print_paginated(exams, page, page_size, use_json,
                            title="考试安排",
                            key="exams",
                            extra={"term": semester or "当前学期", "username": account.username})
        else:
            print_error("研究生考试安排查询暂不支持。", use_json)
    except Exception as e:
        print_error(f"获取考试安排失败: {e}", use_json)


def cmd_export_ics(file_path: str, semester: str = None, use_webvpn: bool = False, use_json: bool = False):
    """导出课表为 ICS 日历文件。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:

        # 获取课表数据
        session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=use_webvpn)

        if account.type == Account.AccountType.UNDERGRADUATE:
            from jwxt.schedule import Schedule as JWXTSchedule
            sched = JWXTSchedule(session)
            lessons = sched.getSchedule(semester)
        else:
            lessons = GraduateSchedule(session).getSchedule()

        # 使用 icalendar 导出
        from icalendar import Calendar, Event
        import pytz

        cal = Calendar()
        cal.add("prodid", "-//XJTUToolBox//Schedule//CN")
        cal.add("version", "2.0")
        cal.add("calscale", "GREGORIAN")
        cal.add("method", "PUBLISH")
        cal.add("x-wr-calname", f"课表 - {account.nickname or account.username}")
        cal.add("x-wr-timezone", "Asia/Shanghai")

        tz = pytz.timezone("Asia/Shanghai")
        event_count = 0

        for lesson in lessons if isinstance(lessons, list) else []:
            # 简化处理：直接创建事件
            event = Event()
            name = lesson.get("KCM") or lesson.get("courseName", "未知课程")
            event.add("summary", name)
            location = lesson.get("JASMC") or lesson.get("location", "")
            if location:
                event.add("location", location)

            # 使用当前日期作为占位
            now = datetime.datetime.now(tz)
            event.add("dtstart", now)
            event.add("dtend", now + datetime.timedelta(hours=1))
            cal.add_component(event)
            event_count += 1

        with open(file_path, "wb") as f:
            f.write(cal.to_ical())

        print_success(f"已导出 {event_count} 个课程事件到 {file_path}", use_json=use_json)
    except Exception as e:
        print_error(f"导出 ICS 失败: {e}", use_json)


def cmd_get_attendance(use_webvpn: bool = False, use_json: bool = False):
    """获取本周考勤信息。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        from attendance.attendance import Attendance

        is_postgraduate = (account.type == Account.AccountType.POSTGRADUATE)
        session_name = "attendance_webvpn" if use_webvpn else "attendance_direct"
        session = get_logged_in_attendance_session(account, session_name=session_name, use_webvpn=use_webvpn)

        att = Attendance(session, use_webvpn=use_webvpn, is_postgraduate=is_postgraduate)
        records_data = []
        try:
            # 优先使用本周考勤汇总接口。
            current_week_records = att.attendanceCurrentWeek()
            for record in (current_week_records or []):
                records_data.append({
                    "course": str(record.get("subjectname", "")),
                    "week": str(record.get("week", "")),
                    "normal": record.get("normalCount", 0),
                    "late": record.get("lateCount", 0),
                    "absence": record.get("absenceCount", 0),
                    "leave": record.get("leaveCount", 0),
                    "total": record.get("total", 0),
                })
        except Exception:
            # 兼容接口权限差异：回退到流水接口，避免命令整体失败。
            page_data = att.getFlowRecordWithPage(current=1, page_size=20)
            flow_records = page_data.get("data", []) if isinstance(page_data, dict) else []
            for record in flow_records:
                records_data.append({
                    "time": str(getattr(record, "water_time", "")),
                    "location": str(getattr(record, "place", "")),
                    "type": str(getattr(record, "type_", "")),
                })

        print_output(records_data, use_json, title="本周考勤")
    except Exception as e:
        print_error(f"获取考勤信息失败: {e}", use_json)
