"""
通知查询 CLI 命令
"""

from cli.output import print_output, print_error, print_success, print_paginated
from cli.session import get_account_manager, require_current_account
from shared.cache import cacheManager


def _load_cached_notifications():
    """从缓存读取通知列表。"""
    try:
        from notification.notification_manager import NotificationManager
        raw = cacheManager.read_json("notification.json")
        return NotificationManager.load_notifications(raw)
    except Exception:
        return []


def _save_cached_notifications(notifications):
    """将通知列表写入缓存。"""
    from notification.notification_manager import NotificationManager
    cacheManager.write_json(
        "notification.json",
        NotificationManager.dump_notifications(notifications),
        allow_overwrite=True,
    )


def _apply_read_state_from_cache(notifications):
    """用缓存中的已读状态覆盖当前抓取结果。"""
    cached = _load_cached_notifications()
    read_keys = {
        (n.title, n.link, n.source.value)
        for n in cached
        if getattr(n, "is_read", False)
    }
    for n in notifications:
        key = (n.title, n.link, n.source.value)
        if key in read_keys:
            n.is_read = True


def get_notification_manager(account):
    """获取通知管理器实例（默认订阅所有来源）。"""
    from notification.notification_manager import NotificationManager
    from notification.source import Source

    manager = NotificationManager()
    for src in Source:
        manager.add_subscription(src)
    return manager


def cmd_list(source: str = None, unread_only: bool = False, page: int = 1, page_size: int = 10,
             use_json: bool = False):
    """查询通知列表。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        notif_mgr = get_notification_manager(account)
        notifications = notif_mgr.get_notifications()
        _apply_read_state_from_cache(notifications)
        _save_cached_notifications(notifications)

        if source:
            source_upper = source.upper()
            notifications = [
                n for n in notifications
                if getattr(n, "source", None)
                and (n.source.name.upper() == source_upper or n.source.value == source)
            ]

        if unread_only:
            notifications = [n for n in notifications if not getattr(n, "is_read", False)]

        # 排序（时间倒序）
        notifications = sorted(notifications, key=lambda n: getattr(n, "date", ""), reverse=True)

        # 转序列化
        serialized = []
        for n in notifications:
            src = getattr(n, "source", None)
            serialized.append({
                "title": getattr(n, "title", ""),
                "source": src.value if hasattr(src, "value") else str(src),
                "publish_time": str(getattr(n, "date", "")),
                "url": getattr(n, "link", ""),
                "is_read": getattr(n, "is_read", False),
            })

        print_paginated(serialized, page, page_size, use_json,
                        title="通知列表",
                        key="notifications",
                        extra={"total_unfiltered": len(notifications)})
    except Exception as e:
        print_error(f"获取通知失败: {e}", use_json)


def cmd_refresh(use_json: bool = False):
    """立刻刷新所有通知。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        notif_mgr = get_notification_manager(account)
        notifications = notif_mgr.get_notifications()
        _apply_read_state_from_cache(notifications)
        _save_cached_notifications(notifications)
        print_success("通知已刷新。", {"count": len(notifications)}, use_json=use_json)
    except Exception as e:
        print_error(f"刷新通知失败: {e}", use_json)


def cmd_mark_all_read(use_json: bool = False):
    """将所有通知标记为已读。"""
    mgr = get_account_manager()
    account = require_current_account(mgr)

    try:
        notifications = _load_cached_notifications()
        if not notifications:
            notif_mgr = get_notification_manager(account)
            notifications = notif_mgr.get_notifications()

        for n in notifications:
            n.is_read = True

        _save_cached_notifications(notifications)
        print_success("所有通知已标记为已读。", {"count": len(notifications)}, use_json=use_json)
    except Exception as e:
        print_error(f"标记已读失败: {e}", use_json)


def cmd_sources(use_json: bool = False):
    """列出可用的通知来源。"""
    from notification.source import Source, get_source_url

    sources = []
    for src_enum in Source:
        sources.append({
            "name": src_enum.name,
            "display_name": src_enum.value,
            "url": get_source_url(src_enum),
        })
    print_output(sources, use_json, title="通知来源")
