"""
考勤流水查询 CLI 命令
"""

from cli.output import print_output, print_error
from cli.session import get_account_manager, require_current_account, get_logged_in_attendance_session
from shared.account import Account


def cmd_flow(page: int = 1, page_size: int = 5, use_webvpn: bool = False, use_json: bool = False):
    """查询考勤流水记录。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        from attendance.attendance import Attendance

        is_postgraduate = (account.type == Account.AccountType.POSTGRADUATE)
        session_name = "attendance_webvpn" if use_webvpn else "attendance_direct"
        session = get_logged_in_attendance_session(account, session_name=session_name, use_webvpn=use_webvpn)

        att = Attendance(session, use_webvpn=use_webvpn, is_postgraduate=is_postgraduate)

        # 使用 Attendance.getFlowRecordWithPage 查询考勤流水
        page_data = att.getFlowRecordWithPage(current=page, page_size=page_size)
        records = page_data.get("data", []) if isinstance(page_data, dict) else []

        records_data = []
        for record in (records or []):
            if hasattr(record, 'json'):
                record_dict = record.json()
            elif hasattr(record, 'to_dict'):
                record_dict = record.to_dict()
            else:
                record_dict = {
                    "time": str(getattr(record, "water_time", "")),
                    "location": str(getattr(record, "place", "")),
                    "type": str(getattr(record, "type_", "")),
                }
            records_data.append(record_dict)

        output_data = {
            "page": page,
            "page_size": page_size,
            "records": records_data,
            "count": len(records_data),
            "total_count": page_data.get("total_count", len(records_data)) if isinstance(page_data, dict) else len(records_data),
            "total_pages": page_data.get("total_pages", 1) if isinstance(page_data, dict) else 1,
        }

        print_output(output_data, use_json, title="考勤流水")
    except Exception as e:
        print_error(f"查询考勤流水失败: {e}", use_json)
