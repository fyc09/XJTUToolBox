"""
WebVPN 网址转换 CLI 命令
"""

from cli.output import print_error, print_success
from auth.util import getVPNUrl, getOrdinaryUrl


def cmd_encode(url: str, use_json: bool = False):
    """将普通网址转换为 WebVPN 网址。"""
    try:
        vpn_url = getVPNUrl(url)
        print_success("转换成功", {"original": url, "webvpn_url": vpn_url}, use_json)
    except Exception as e:
        print_error(f"转换失败: {e}", use_json)


def cmd_decode(url: str, use_json: bool = False):
    """将 WebVPN 网址还原为普通网址。"""
    try:
        normal_url = getOrdinaryUrl(url)
        print_success("解析成功", {"webvpn_url": url, "normal_url": normal_url}, use_json)
    except Exception as e:
        print_error(f"解析失败: {e}", use_json)
