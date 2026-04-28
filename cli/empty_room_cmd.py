"""
空闲教室查询 CLI 命令
"""

from cli.output import print_error, print_success, print_paginated
from cli.session import get_account_manager, require_current_account, get_logged_in_session
from auth.constant import JWXT_LOGIN_URL
import datetime


# 校区代码映射
CAMPUS_MAP = {
    "兴庆": "01",
    "雁塔": "03",
    "创新港": "04",
    "曲江": "02",
    "苏州": "XB14",
}


def cmd_query(
    campus: str = "兴庆",
    building: str = None,
    date: str = None,
    page: int = 1,
    page_size: int = 10,
    use_cf: bool = False,
    use_json: bool = False,
):
    """查询空闲教室。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    date = date or datetime.date.today().isoformat()

    if use_cf:
        return _query_cf(account, campus, building, date, page, page_size, use_json)
    else:
        return _query_direct(account, campus, building, date, page, page_size, use_json)


def _query_direct(account, campus, building, date, page, page_size, use_json):
    try:
        from jwxt.empty_room import EmptyRoom, CAMPUS_BUILDING_DICT

        session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=False)
        er = EmptyRoom(session)

        # 获取校区代码
        campus_code = CAMPUS_MAP.get(campus)
        if not campus_code:
            print_error(f"未知校区: {campus}。可选: {', '.join(CAMPUS_MAP.keys())}", use_json)
            return

        # 获取该校区所有教学楼
        buildings = CAMPUS_BUILDING_DICT.get(campus, [])
        if building and building not in buildings:
            print_error(f"校区 {campus} 下没有教学楼: {building}", use_json)
            return

        buildings_to_query = [building] if building else buildings
        all_rooms = []

        for bld in buildings_to_query:
            try:
                rooms = er.getEmptyRoom(campus_code, bld, date, 1, 11)
                all_rooms.extend(rooms or [])
            except Exception:
                pass

        print_paginated(all_rooms, page, page_size, use_json,
                        title="空闲教室",
                        key="rooms",
                        extra={
                            "campus": campus,
                            "date": date,
                            "buildings_queried": buildings_to_query,
                        })

    except Exception as e:
        print_error(f"查询空闲教室失败: {e}", use_json)


def _query_cf(account, campus, building, date, page, page_size, use_json):
    """通过 Cloudflare CDN 查询（无需登录，但研究生只能通过此方式）。"""
    try:
        import requests

        # 从 ywtb 获取 CF 数据
        cf_url = "https://empty-room-cdn.xjtu.edu.cn/data"
        params = {
            "campus": campus,
            "date": date,
        }
        if building:
            params["building"] = building

        resp = requests.get(cf_url, params=params, timeout=30)
        data = resp.json()

        rooms = data.get("rooms", data)
        if not isinstance(rooms, list):
            rooms = []

        print_paginated(rooms, page, page_size, use_json,
                        title="空闲教室 (CDN)",
                        key="rooms",
                        extra={
                            "campus": campus,
                            "date": date,
                            "source": "cloudflare_cdn",
                        })

    except Exception as e:
        print_error(f"通过 CDN 查询空闲教室失败: {e}", use_json)


def cmd_export_image(file_path: str, campus: str = "兴庆", date: str = None, use_json: bool = False):
    """导出空闲教室为 PNG 图片。"""
    # 先查询数据
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print_error("导出图片需要 pillow 库: pip install pillow", use_json)
        return

    mgr = get_account_manager()
    account = require_current_account(mgr)
    date = date or datetime.date.today().isoformat()

    try:
        from jwxt.empty_room import EmptyRoom, CAMPUS_BUILDING_DICT
        session = get_logged_in_session(account, login_url=JWXT_LOGIN_URL, use_webvpn=False)
        er = EmptyRoom(session)

        campus_code = CAMPUS_MAP.get(campus)
        if not campus_code:
            print_error(f"未知校区: {campus}", use_json)
            return

        buildings = CAMPUS_BUILDING_DICT.get(campus, [])
        all_rooms = []
        for bld in buildings:
            try:
                rooms = er.getEmptyRoom(campus_code, bld, date, 1, 11)
                all_rooms.extend(rooms or [])
            except Exception:
                pass

        # 生成表格图片
        img = Image.new("RGB", (1200, 400 + len(all_rooms) * 30), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("msyh.ttc", 14)
        except OSError:
            font = ImageFont.load_default()

        y = 10
        draw.text((10, y), f"空闲教室 - {campus} - {date}", fill="black", font=font)
        y += 30

        # 表头
        headers = ["教室", "1-2节", "3-4节", "5-6节", "7-8节", "9-11节"]
        x = 10
        for h in headers:
            draw.text((x, y), h, fill="black", font=font)
            x += 150
        y += 25

        for room in all_rooms:
            x = 10
            name = room.get("name", "")
            draw.text((x, y), name, fill="black", font=font)
            for cell in range(5):
                draw.text((x + 150 * (cell + 1), y), "空闲", fill="green", font=font)
            y += 25

        img.save(file_path)
        print_success(f"已导出空闲教室图片到 {file_path}", use_json=use_json)

    except Exception as e:
        print_error(f"导出图片失败: {e}", use_json)
