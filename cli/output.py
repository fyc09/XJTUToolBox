"""
输出格式化工具 — JSON / 可读文本 双模式

所有 CLI 命令通过此模块输出结果，保证格式统一。
"""

import json
import math
import sys
from typing import Any, Tuple, Optional


def _serialize(obj: Any) -> Any:
    """递归将对象序列化为 JSON 友好的类型。"""
    if hasattr(obj, "to_diction"):
        return _serialize(obj.to_diction())
    if hasattr(obj, "_asdict"):
        return _serialize(obj._asdict())
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    if isinstance(obj, Enum):
        return obj.name if hasattr(obj, "name") else str(obj)
    # 处理 datetime / date
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


from enum import Enum


def paginate_items(items: list, page: int = 1, page_size: int = 10) -> Tuple[list, dict]:
    """
    对列表进行分页。
    
    :param items: 完整列表
    :param page: 页码（从 1 开始）
    :param page_size: 每页条数
    :returns: (当前页条目, 分页元信息)
    """
    total = len(items)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    meta = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
    }
    return page_items, meta


def print_paginated(items: list, page: int, page_size: int,
                    use_json: bool, *,
                    title: str = "",
                    key: str = "items",
                    extra: Optional[dict] = None) -> None:
    """
    输出分页数据。
    
    :param items: 完整的数据列表
    :param page: 当前页码
    :param page_size: 每页条数
    :param use_json: 是否 JSON 输出
    :param title: 文本模式标题
    :param key: JSON 模式条目键名
    :param extra: 额外附加到 JSON 输出的数据
    """
    page_items, meta = paginate_items(items, page, page_size)

    if use_json:
        output = dict(meta)
        output[key] = page_items
        if extra:
            output.update(extra)
        print(json.dumps(_serialize(output), ensure_ascii=False, indent=2, default=str))
    else:
        lines = []
        if title:
            lines.append(f"=== {title} ===")
        lines.append(f"--- 第 {meta['page']}/{meta['total_pages']} 页（共 {meta['total']} 条）---")
        lines.append("")
        for i, item in enumerate(page_items, 1):
            if isinstance(item, dict):
                lines.append(f"[{i}]")
                for k, v in item.items():
                    lines.append(f"  {k}: {v}")
                lines.append("")
            else:
                lines.append(f"[{i}] {item}")
        if meta["has_next"]:
            lines.append(f"--- 还有 {meta['total'] - meta['page'] * meta['page_size']} 条，使用 --page {meta['page'] + 1} 查看下一页 ---")
        print("\n".join(lines).strip())


def format_output(data: Any, use_json: bool = False, title: str = "") -> str:
    """
    格式化输出。

    :param data: 要输出的数据（dict, list, dataclass, Account 等）
    :param use_json: 为 True 时输出 JSON，否则输出可读文本
    :param title: 可读模式的可选标题
    :returns: 格式化后的字符串
    """
    serialized = _serialize(data)

    if use_json:
        return json.dumps(serialized, ensure_ascii=False, indent=2, default=str)

    # 可读文本模式
    lines = []
    if title:
        lines.append(f"=== {title} ===")

    if isinstance(serialized, dict):
        for k, v in serialized.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{k}:")
                lines.append(json.dumps(v, ensure_ascii=False, indent=2, default=str))
            else:
                lines.append(f"{k}: {v}")
    elif isinstance(serialized, list):
        for i, item in enumerate(serialized, 1):
            if isinstance(item, dict):
                lines.append(f"[{i}]")
                for k, v in item.items():
                    lines.append(f"  {k}: {v}")
                lines.append("")
            else:
                lines.append(f"[{i}] {item}")
    else:
        lines.append(str(serialized))

    return "\n".join(lines).strip()


def print_output(data: Any, use_json: bool = False, title: str = "") -> None:
    """将格式化结果输出到 stdout（JSON 模式）或 stdout + 信息（文本模式）。"""
    text = format_output(data, use_json, title)
    if use_json:
        # JSON 模式：纯净 JSON 到 stdout，其他信息到 stderr
        print(text)
    else:
        print(text)


def print_error(message: str, use_json: bool = False) -> None:
    """输出错误信息。"""
    if use_json:
        obj = {"success": False, "error": message}
        print(json.dumps(obj, ensure_ascii=False))
    else:
        print(f"错误: {message}", file=sys.stderr)


def print_success(message: str, data: Any = None, use_json: bool = False) -> None:
    """输出成功信息，可选附带数据。"""
    if use_json:
        obj = {"success": True, "message": message}
        if data is not None:
            obj["data"] = _serialize(data)
        print(json.dumps(obj, ensure_ascii=False))
    else:
        print(f"✓ {message}")
        if data is not None:
            print(format_output(data, use_json=False))
