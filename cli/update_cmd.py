"""
更新检查 CLI 命令
"""

import sys

import requests

from cli.output import print_output, print_error
from shared.config import cfg
from shared.update_checker import (
    fetch_latest_release_info,
    get_download_url_from_assets,
    generate_cloudflare_service_url,
    is_github_rate_limited,
)
from packaging.version import parse


def cmd_check(use_prerelease: bool = False, use_json: bool = False):
    """检查更新"""
    try:
        prerelease_enabled = bool(use_prerelease or cfg.prereleaseEnable.value)
        release = fetch_latest_release_info(prerelease=prerelease_enabled)

        version = str(release.get("tag_name", ""))
        release_notes = release.get("body", "") or ""
        asset_url, total_size = get_download_url_from_assets(release.get("assets", []) or [])
        cloudflare_asset_url = generate_cloudflare_service_url(version, asset_url) if asset_url else None

        if parse(version) > cfg.version:
            status = "UPDATE_AVAILABLE"
            if asset_url and cloudflare_asset_url and getattr(sys, "frozen", False):
                status = "UPDATE_EXE_AVAILABLE"
            output_data = {
                "current_version": str(cfg.version),
                "latest_version": str(parse(version)),
                "has_update": True,
                "status": status,
                "release_notes": release_notes,
                "asset_urls": [asset_url, cloudflare_asset_url],
                "total_size": total_size,
                "prerelease_enabled": prerelease_enabled,
            }
            print_output(output_data, use_json, title="更新检查")
        else:
            output_data = {
                "current_version": str(cfg.version),
                "has_update": False,
                "status": "NO_UPDATE",
                "message": "当前已是最新版本。",
                "prerelease_enabled": prerelease_enabled,
            }
            print_output(output_data, use_json, title="更新检查")
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            print_output(
                {
                    "current_version": str(cfg.version),
                    "has_update": False,
                    "status": "NO_UPDATE",
                    "message": "当前已是最新版本。",
                },
                use_json,
                title="更新检查",
            )
            return

        if is_github_rate_limited(e):
            print_error("检查更新失败: GitHub API 超出请求限制，请尝试关闭代理", use_json)
            return

        print_error(f"检查更新失败: {e}", use_json)
    except Exception as e:
        print_error(f"检查更新失败: {e}", use_json)
