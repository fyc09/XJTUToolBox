"""
更新检查公共逻辑
封装 GitHub Release 查询、平台资产匹配、镜像 URL 生成，
供 GUI UpdateThread 和 CLI update_cmd 共用。
"""

import platform

import requests
from packaging.version import parse

from shared.fastest_mirror import FastestMirror


# 仓库标识
REPO_OWNER = "yan-xiaoo"
REPO_NAME = "XJTUToolbox"


def fetch_latest_release_info(prerelease: bool, timeout: int = 10) -> dict:
    """
    获取最新的发布信息。

    :param prerelease: 是否包含预发布版本
    :param timeout: 请求超时秒数
    :returns: 发布信息字典（单条）
    :raises requests.RequestException: 网络错误
    :raises ValueError: 响应格式不符合预期
    """
    url = FastestMirror.get_github_api_mirror(REPO_OWNER, REPO_NAME, latest=not prerelease)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()

    if prerelease:
        # /releases 返回列表，取第一条
        if isinstance(data, list) and data:
            return data[0]
        raise ValueError("未获取到预发布版本信息")

    # /releases/latest 返回单个对象；稳妥起见也兼容列表
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data:
        return data[0]
    raise ValueError("发布信息格式不正确")


def get_download_url_from_assets(assets):
    """
    从发布资产中选择当前平台的下载链接。

    :param assets: 发布资产列表
    :returns: (下载URL, 文件大小) 元组，未匹配到时返回 (None, 0)
    """
    system = platform.system()
    if system == "Windows":
        for asset in assets:
            name = str(asset.get("name", "")).lower()
            if "windows" in name:
                return asset.get("browser_download_url"), asset.get("size", 0)
    elif system == "Darwin":
        arc = platform.machine()
        if arc == "arm64":
            for asset in assets:
                if "arm64" in str(asset.get("name", "")).lower():
                    return asset.get("browser_download_url"), asset.get("size", 0)
        elif arc == "x86_64":
            for asset in assets:
                if "x86_64" in str(asset.get("name", "")).lower():
                    return asset.get("browser_download_url"), asset.get("size", 0)
    return None, 0


def generate_cloudflare_service_url(version: str, original_download_url: str) -> str:
    """
    生成 Cloudflare Workers CDN 回源 URL。

    :param version: 版本号（含 v 前缀，如 v1.1.4）
    :param original_download_url: GitHub Release 原始下载 URL
    :returns: Cloudflare CDN URL
    """
    file_name = original_download_url.split("/")[-1]
    return f"https://gh-release.xjtutoolbox.com/?file=releases/{version}/{file_name}"


def is_github_rate_limited(error: requests.HTTPError) -> bool:
    """
    判断 HTTP 错误是否为 GitHub API 速率限制。

    :param error: 捕获到的 HTTPError
    :returns: True 表示触发了速率限制
    """
    return (
        error.response is not None
        and error.response.status_code == 403
        and "rate limit exceeded for url" in str(error).lower()
    )
