"""
配置管理 CLI 命令
"""

from cli.output import print_output, print_error, print_success
from shared.config import cfg


def cmd_list(use_json: bool = False):
    """列出所有配置项。"""
    config_items = {}

    # 收集所有配置项
    for attr_name in dir(cfg):
        if attr_name.startswith("_"):
            continue
        attr = getattr(cfg, attr_name, None)
        # 检查是否是配置项
        if hasattr(attr, "value"):
            config_items[attr_name] = {
                "value": str(attr.value),
                "default": str(getattr(cfg, f"_{attr_name}_default", "")),
            }

    print_output(config_items, use_json, title="配置列表")


def cmd_get(key: str, use_json: bool = False):
    """获取配置项的值。"""
    if not hasattr(cfg, key):
        print_error(f"未知配置项: {key}", use_json)
        return

    attr = getattr(cfg, key)
    if hasattr(attr, "value"):
        value = attr.value
    else:
        value = attr

    print_output({key: str(value)}, use_json)


def cmd_set(key: str, value: str, use_json: bool = False):
    """设置配置项的值。"""
    if not hasattr(cfg, key):
        print_error(f"未知配置项: {key}", use_json)
        return

    attr = getattr(cfg, key)
    if not hasattr(attr, "value"):
        print_error(f"配置项 {key} 不可修改。", use_json)
        return

    # 尝试转换值类型
    from qfluentwidgets import OptionsConfigItem
    import datetime

    try:
        if isinstance(attr, OptionsConfigItem):
            # 对于选项型配置，直接尝试设置
            if isinstance(attr.value, bool):
                attr.value = value.lower() in ("true", "1", "yes")
            elif isinstance(attr.value, int):
                attr.value = int(value)
            elif isinstance(attr.value, datetime.time):
                parts = value.split(":")
                attr.value = datetime.time(hour=int(parts[0]), minute=int(parts[1]))
            else:
                attr.value = type(attr.value)(value)
        else:
            attr.value = value
    except (ValueError, TypeError) as e:
        print_error(f"设置失败: {e}", use_json)
        return

    # 保存配置
    try:
        from qfluentwidgets import qconfig
        qconfig.save()
        print_success(f"已设置 {key} = {attr.value}", use_json=use_json)
    except Exception:
        print_success(f"已设置 {key} = {attr.value}（配置可能未持久化到文件）", use_json=use_json)
