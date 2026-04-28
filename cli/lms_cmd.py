"""
思源学堂 CLI 命令
"""

from cli.output import print_output, print_error, print_success, print_paginated
from cli.session import get_account_manager, require_current_account, get_logged_in_session
from auth.constant import LMS_LOGIN_URL


def _get_lms_util(account):
    """获取 LMSUtil 实例。"""
    from lms.lms import LMSUtil
    session = get_logged_in_session(account, login_url=LMS_LOGIN_URL)
    return LMSUtil(session)


def cmd_courses(page: int = 1, page_size: int = 10, use_json: bool = False):
    """列出思源学堂课程。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        lms = _get_lms_util(account)
        courses = lms.get_my_courses()

        serialized = []
        for c in (courses or []):
            serialized.append({
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "course_code": c.get("course_code", ""),
                "instructors": c.get("instructors", []),
                "completeness": c.get("study_completeness", 0),
            })

        print_paginated(serialized, page, page_size, use_json,
                        title="思源学堂课程列表",
                        key="courses")
    except Exception as e:
        print_error(f"获取课程列表失败: {e}", use_json)


def cmd_activities(course_id: int, activity_type: str = None,
                   page: int = 1, page_size: int = 10, use_json: bool = False):
    """列出课程活动。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        lms = _get_lms_util(account)
        activities = lms.get_course_activities(course_id)

        serialized = []
        for a in (activities or []):
            atype = a.get("type", "")
            if activity_type and atype != activity_type:
                continue
            serialized.append({
                "id": a.get("id", ""),
                "title": a.get("title", ""),
                "type": atype,
                "start_time": str(a.get("start_time", "")),
                "end_time": str(a.get("end_time", "")),
                "published": a.get("published", False),
            })

        print_paginated(serialized, page, page_size, use_json,
                        title="课程活动列表",
                        key="activities",
                        extra={"course_id": course_id, "activity_type_filter": activity_type})
    except Exception as e:
        print_error(f"获取活动列表失败: {e}", use_json)


def cmd_detail(activity_id: int, use_json: bool = False):
    """查看活动详情。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        lms = _get_lms_util(account)
        detail = lms.get_activity_detail(activity_id)

        print_output(detail, use_json, title="活动详情")
    except Exception as e:
        print_error(f"获取活动详情失败: {e}", use_json)


def cmd_download(activity_id: int, file_id: int = None, output_dir: str = ".", use_json: bool = False):
    """下载活动附件。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        import os

        lms = _get_lms_util(account)
        detail = lms.get_activity_detail(activity_id)

        # 查找附件
        uploads = detail.get("submission_list", {}).get("uploads", []) if isinstance(detail, dict) else []
        if not uploads:
            print_error("该活动没有附件。", use_json)
            return

        downloaded = []
        for upload in uploads:
            if file_id and upload.get("id") != file_id:
                continue
            file_name = upload.get("name", f"file_{upload.get('id')}")
            file_url = upload.get("download_url", "")
            if file_url:
                import requests
                resp = requests.get(file_url, timeout=60)
                file_path = os.path.join(output_dir, file_name)
                with open(file_path, "wb") as f:
                    f.write(resp.content)
                downloaded.append(file_path)

        if downloaded:
            print_success(f"已下载 {len(downloaded)} 个文件: {', '.join(downloaded)}", use_json=use_json)
        else:
            print_error("未找到匹配的附件。", use_json)
    except Exception as e:
        print_error(f"下载附件失败: {e}", use_json)
