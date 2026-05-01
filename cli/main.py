"""
XJTUToolBox CLI — 命令行工具入口

覆盖 GUI 全部功能，支持 --json 参数输出结构化数据供 AI 解析。

用法:
  xjtutoolbox [全局选项] <命令> [子命令] [选项]

全局选项:
  --json    以 JSON 格式输出结果（AI 友好）
  --help    显示帮助信息

示例:
  xjtutoolbox --json schedule get --week 6
  xjtutoolbox score query --semester "2024-2025-2"
  xjtutoolbox account list
"""

import sys
import os

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import click


# ========== 全局选项上下文 ==========

class CliContext:
    """全局 CLI 上下文，存储 --json 等全局选项。"""
    def __init__(self, use_json: bool = False):
        self.use_json = use_json


pass_ctx = click.make_pass_decorator(CliContext, ensure=True)


# ========== 主 CLI 组 ==========

@click.group(invoke_without_command=False)
@click.option("--json", "use_json", is_flag=True, help="以 JSON 格式输出（AI 友好）")
@click.version_option(version="1.2.4", message="XJTUToolBox CLI v%(version)s")
@pass_ctx
def cli(ctx, use_json: bool):
    """XJTUToolBox — 西安交通大学校园服务命令行工具"""
    ctx.use_json = use_json


# ========== account 子命令组 ==========

@cli.group()
def account():
    """账户管理：列出、切换、删除、加解密"""


@account.command("list")
@pass_ctx
def account_list(ctx):
    """列出所有已保存的账户"""
    from cli.account_cmd import cmd_list
    cmd_list(use_json=ctx.use_json)


@account.command("switch")
@click.argument("uuid")
@pass_ctx
def account_switch(ctx, uuid: str):
    """切换当前账户"""
    from cli.account_cmd import cmd_switch
    cmd_switch(uuid, use_json=ctx.use_json)


@account.command("remove")
@click.argument("uuid")
@pass_ctx
def account_remove(ctx, uuid: str):
    """删除指定账户"""
    from cli.account_cmd import cmd_remove
    cmd_remove(uuid, use_json=ctx.use_json)


@account.command("encrypt")
@click.option("--password", "-p", required=True, help="加密密码")
@pass_ctx
def account_encrypt(ctx, password: str):
    """加密所有账户数据"""
    from cli.account_cmd import cmd_set_encrypted
    cmd_set_encrypted(True, password=password, use_json=ctx.use_json)


@account.command("decrypt")
@click.option("--password", "-p", help="解密密码（如果已加密）")
@pass_ctx
def account_decrypt(ctx, password: str = None):
    """解密账户数据"""
    from cli.account_cmd import cmd_set_encrypted
    cmd_set_encrypted(False, password=password, use_json=ctx.use_json)


# ========== schedule 子命令组 ==========

@cli.group()
def schedule():
    """课表查询与导出"""


@schedule.command("get")
@click.option("--semester", "-s", help="学年学期，如 2024-2025-2")
@click.option("--week", "-w", type=int, help="周次")
@click.option("--page", "-p", type=int, default=1, help="页码（默认 1）")
@click.option("--page-size", "-n", type=int, default=10, help="每页条数（默认 10）")
@click.option("--webvpn", is_flag=True, help="通过 WebVPN 登录")
@pass_ctx
def schedule_get(ctx, semester: str = None, week: int = None, page: int = 1, page_size: int = 10, webvpn: bool = False):
    """获取课表"""
    from cli.schedule_cmd import cmd_get
    cmd_get(semester=semester, week=week, page=page, page_size=page_size, use_webvpn=webvpn, use_json=ctx.use_json)


@schedule.command("exam")
@click.option("--semester", "-s", help="学年学期")
@click.option("--page", "-p", type=int, default=1, help="页码（默认 1）")
@click.option("--page-size", "-n", type=int, default=10, help="每页条数（默认 10）")
@click.option("--webvpn", is_flag=True, help="通过 WebVPN 登录")
@pass_ctx
def schedule_exam(ctx, semester: str = None, page: int = 1, page_size: int = 10, webvpn: bool = False):
    """获取考试安排"""
    from cli.schedule_cmd import cmd_exam
    cmd_exam(semester=semester, page=page, page_size=page_size, use_webvpn=webvpn, use_json=ctx.use_json)


@schedule.command("export-ics")
@click.argument("output", type=click.Path())
@click.option("--semester", "-s", help="学年学期")
@click.option("--webvpn", is_flag=True)
@pass_ctx
def schedule_export_ics(ctx, output: str, semester: str = None, webvpn: bool = False):
    """导出课表为 ICS 日历文件"""
    from cli.schedule_cmd import cmd_export_ics
    cmd_export_ics(output, semester=semester, use_webvpn=webvpn, use_json=ctx.use_json)


@schedule.command("attendance")
@click.option("--webvpn", is_flag=True)
@pass_ctx
def schedule_attendance(ctx, webvpn: bool = False):
    """获取本周考勤记录"""
    from cli.schedule_cmd import cmd_get_attendance
    cmd_get_attendance(use_webvpn=webvpn, use_json=ctx.use_json)


# ========== score 子命令组 ==========

@cli.group()
def score():
    """成绩查询"""


@score.command("query")
@click.option("--semester", "-s", help="学年学期，如 2024-2025-2")
@click.option("--page", "-p", type=int, default=1, help="页码（默认 1）")
@click.option("--page-size", "-n", type=int, default=10, help="每页条数（默认 10）")
@click.option("--webvpn", is_flag=True, help="通过 WebVPN 登录")
@pass_ctx
def score_query(ctx, semester: str = None, page: int = 1, page_size: int = 10, webvpn: bool = False):
    """查询成绩"""
    from cli.score_cmd import cmd_query
    cmd_query(semester=semester, page=page, page_size=page_size, use_webvpn=webvpn, use_json=ctx.use_json)


# ========== attendance 子命令组 ==========

@cli.group()
def attendance():
    """考勤流水查询"""


@attendance.command("flow")
@click.option("--page", "-p", type=int, default=1, help="页码")
@click.option("--page-size", type=int, default=5, help="每页条数")
@click.option("--webvpn", is_flag=True)
@pass_ctx
def attendance_flow(ctx, page: int = 1, page_size: int = 5, webvpn: bool = False):
    """查询考勤流水"""
    from cli.attendance_cmd import cmd_flow
    cmd_flow(page=page, page_size=page_size, use_webvpn=webvpn, use_json=ctx.use_json)


# ========== judge 子命令组 ==========

@cli.group()
def judge():
    """评教管理"""


@judge.command("list")
@click.option("--show-completed", is_flag=True, help="显示已完成的评教")
@click.option("--webvpn", is_flag=True)
@pass_ctx
def judge_list(ctx, show_completed: bool = False, webvpn: bool = False):
    """列出评教问卷"""
    from cli.judge_cmd import cmd_list
    cmd_list(show_completed=show_completed, use_webvpn=webvpn, use_json=ctx.use_json)


@judge.command("all")
@click.option("--score", "-s", default="95", help="评教分数（默认 95）")
@click.option("--comment", "-c", default="老师讲得很好，课程内容充实。", help="评教评语")
@click.option("--webvpn", is_flag=True)
@pass_ctx
def judge_all(ctx, score: str = "95", comment: str = "老师讲得很好，课程内容充实。", webvpn: bool = False):
    """一键全部评教"""
    from cli.judge_cmd import cmd_all
    cmd_all(score=score, comment=comment, use_webvpn=webvpn, use_json=ctx.use_json)


# ========== empty-room 子命令组 ==========

@cli.group(name="empty-room")
def empty_room():
    """空闲教室查询"""


@empty_room.command("query")
@click.option("--campus", "-c", default="兴庆", help="校区（兴庆/雁塔/创新港/曲江/苏州）")
@click.option("--building", "-b", help="教学楼")
@click.option("--date", "-d", help="日期（YYYY-MM-DD），默认今天")
@click.option("--page", "-p", type=int, default=1, help="页码（默认 1）")
@click.option("--page-size", "-n", type=int, default=10, help="每页条数（默认 10）")
@click.option("--cf", is_flag=True, help="通过 Cloudflare CDN 查询")
@pass_ctx
def empty_room_query(ctx, campus: str = "兴庆", building: str = None, date: str = None,
                     page: int = 1, page_size: int = 10, cf: bool = False):
    """查询空闲教室"""
    from cli.empty_room_cmd import cmd_query
    cmd_query(campus=campus, building=building, date=date, page=page, page_size=page_size, use_cf=cf, use_json=ctx.use_json)


@empty_room.command("export")
@click.argument("output", type=click.Path())
@click.option("--campus", "-c", default="兴庆")
@click.option("--date", "-d", help="日期")
@pass_ctx
def empty_room_export(ctx, output: str, campus: str = "兴庆", date: str = None):
    """导出空闲教室为图片"""
    from cli.empty_room_cmd import cmd_export_image
    cmd_export_image(output, campus=campus, date=date, use_json=ctx.use_json)


# ========== notice 子命令组 ==========

@cli.group()
def notice():
    """通知查询与管理"""


@notice.command("list")
@click.option("--source", "-s", help="通知来源筛选")
@click.option("--unread", is_flag=True, help="仅显示未读")
@click.option("--page", "-p", type=int, default=1, help="页码（默认 1）")
@click.option("--page-size", "-n", type=int, default=10, help="每页条数（默认 10）")
@pass_ctx
def notice_list(ctx, source: str = None, unread: bool = False, page: int = 1, page_size: int = 10):
    """查看通知列表"""
    from cli.notice_cmd import cmd_list
    cmd_list(source=source, unread_only=unread, page=page, page_size=page_size, use_json=ctx.use_json)


@notice.command("refresh")
@pass_ctx
def notice_refresh(ctx):
    """立刻刷新通知"""
    from cli.notice_cmd import cmd_refresh
    cmd_refresh(use_json=ctx.use_json)


@notice.command("mark-read")
@pass_ctx
def notice_mark_read(ctx):
    """全部标记已读"""
    from cli.notice_cmd import cmd_mark_all_read
    cmd_mark_all_read(use_json=ctx.use_json)


@notice.command("sources")
@pass_ctx
def notice_sources(ctx):
    """列出通知来源"""
    from cli.notice_cmd import cmd_sources
    cmd_sources(use_json=ctx.use_json)


# ========== lms 子命令组 ==========

@cli.group()
def lms():
    """思源学堂"""


@lms.command("courses")
@click.option("--page", "-p", type=int, default=1, help="页码（默认 1）")
@click.option("--page-size", "-n", type=int, default=10, help="每页条数（默认 10）")
@pass_ctx
def lms_courses(ctx, page: int = 1, page_size: int = 10):
    """列出课程"""
    from cli.lms_cmd import cmd_courses
    cmd_courses(page=page, page_size=page_size, use_json=ctx.use_json)


@lms.command("activities")
@click.argument("course_id", type=int)
@click.option("--type", "-t", "activity_type", help="活动类型筛选")
@click.option("--page", "-p", type=int, default=1, help="页码（默认 1）")
@click.option("--page-size", "-n", type=int, default=10, help="每页条数（默认 10）")
@pass_ctx
def lms_activities(ctx, course_id: int, activity_type: str = None, page: int = 1, page_size: int = 10):
    """列出课程活动"""
    from cli.lms_cmd import cmd_activities
    cmd_activities(course_id, activity_type=activity_type, page=page, page_size=page_size, use_json=ctx.use_json)


@lms.command("detail")
@click.argument("activity_id", type=int)
@pass_ctx
def lms_detail(ctx, activity_id: int):
    """查看活动详情"""
    from cli.lms_cmd import cmd_detail
    cmd_detail(activity_id, use_json=ctx.use_json)


@lms.command("download")
@click.argument("activity_id", type=int)
@click.option("--file-id", type=int, help="附件 ID（可选）")
@click.option("--output-dir", "-o", default=".", help="下载目录")
@pass_ctx
def lms_download(ctx, activity_id: int, file_id: int = None, output_dir: str = "."):
    """下载活动附件"""
    from cli.lms_cmd import cmd_download
    cmd_download(activity_id, file_id=file_id, output_dir=output_dir, use_json=ctx.use_json)


# ========== webvpn 子命令组 ==========

@cli.group()
def webvpn():
    """WebVPN 网址转换"""


@webvpn.command("encode")
@click.argument("url")
@pass_ctx
def webvpn_encode(ctx, url: str):
    """普通网址 → WebVPN 网址"""
    from cli.webvpn_cmd import cmd_encode
    cmd_encode(url, use_json=ctx.use_json)


@webvpn.command("decode")
@click.argument("url")
@pass_ctx
def webvpn_decode(ctx, url: str):
    """WebVPN 网址 → 普通网址"""
    from cli.webvpn_cmd import cmd_decode
    cmd_decode(url, use_json=ctx.use_json)


# ========== config 子命令组 ==========

@cli.group()
def config():
    """配置管理"""


@config.command("list")
@pass_ctx
def config_list(ctx):
    """列出所有配置项"""
    from cli.config_cmd import cmd_list
    cmd_list(use_json=ctx.use_json)


@config.command("get")
@click.argument("key")
@pass_ctx
def config_get(ctx, key: str):
    """获取配置项值"""
    from cli.config_cmd import cmd_get
    cmd_get(key, use_json=ctx.use_json)


@config.command("set")
@click.argument("key")
@click.argument("value")
@pass_ctx
def config_set(ctx, key: str, value: str):
    """设置配置项值"""
    from cli.config_cmd import cmd_set
    cmd_set(key, value, use_json=ctx.use_json)


# ========== update 子命令组 ==========

@cli.group()
def update():
    """更新检查"""


@update.command("check")
@click.option("--prerelease", is_flag=True, help="检查预发布版本")
@pass_ctx
def update_check(ctx, prerelease: bool = False):
    """检查更新"""
    from cli.update_cmd import cmd_check
    cmd_check(use_prerelease=prerelease, use_json=ctx.use_json)


# ========== 启动入口 ==========

def main():
    """CLI 入口函数。"""
    cli()


if __name__ == "__main__":
    main()
