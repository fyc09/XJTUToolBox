"""
CLI 会话管理 — 复用 auth/ 统一认证 + app/utils/ 账户管理

提供 CLI 友好的登录/切换账户/获取 session 的封装。
"""

import sys
import os

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from typing import Optional
from auth.new_login import NewLogin, NewWebVPNLogin
from auth.constant import JWXT_LOGIN_URL, WEBVPN_LOGIN_URL
from auth.util import get_session
from shared.account import Account, AccountManager
from shared.config import cfg
from shared.migrate_data import DATA_DIRECTORY


def get_account_manager() -> AccountManager:
    """
    获取已加载的 AccountManager 实例。
    由于 CLI 不创建 QApplication，需手动处理账户加载（跳过 Qt 信号）。
    """
    from shared.account import accounts as _accounts
    return _accounts


def require_current_account(accounts_mgr: AccountManager) -> Account:
    """确保当前有选中的账户，否则退出。"""
    if not accounts_mgr.accounts:
        print("错误: 没有已登录的账户。请先在 GUI 中登录一个账户后再使用 CLI。", file=sys.stderr)
        sys.exit(1)
    if accounts_mgr.current is None:
        # 如果没有当前账户但有账户列表，自动选择第一个
        accounts_mgr.current = accounts_mgr.accounts[0]
    return accounts_mgr.current


def login_and_get_session(
    account: Account,
    login_url: str = JWXT_LOGIN_URL,
    use_webvpn: bool = False,
    visitor_id: Optional[str] = None,
) -> object:
    """
    使用账户信息执行登录，并更新 account 的 session_manager。

    这是一个 CLI 友好的阻塞式登录流程（无验证码交互）。

    :param account: Account 对象（需包含 username, password）
    :param login_url: 目标系统登录 URL
    :param use_webvpn: 是否通过 WebVPN 登录
    :param visitor_id: 设备指纹 ID，默认使用 cfg.loginId
    :returns: 已登录的 requests.Session 对象
    """
    session = get_session(fit_system=True)
    visitor_id = visitor_id or cfg.loginId.value

    if use_webvpn:
        login = NewWebVPNLogin(login_url, session, visitor_id)
    else:
        login = NewLogin(login_url, session, visitor_id)

    # 检查是否需要验证码
    try:
        need_captcha = login.isShowJCaptchaCode()
    except Exception:
        need_captcha = False

    jcaptcha = ""

    if need_captcha:
        # 交互式获取验证码
        print("需要验证码才能登录。", file=sys.stderr)
        login.getJCaptchaCode()
        captcha_path = os.path.join(DATA_DIRECTORY, "captcha.png")
        # 需要导入 save 方法 - 实际上 login 有 saveJCaptchaCode
        login.saveJCaptchaCode(captcha_path)
        print(f"验证码已保存到: {captcha_path}", file=sys.stderr)
        print("请打开该图片，输入验证码:", file=sys.stderr, end=" ")
        jcaptcha = input().strip()
        if not jcaptcha:
            print("未输入验证码，取消登录。", file=sys.stderr)
            sys.exit(1)
        # 清理验证码文件
        try:
            os.remove(captcha_path)
        except OSError:
            pass

    # 执行登录
    login.login_or_raise(
        username=account.username,
        password=account.password,
        jcaptcha=jcaptcha,
        account_type=account.type or Account.AccountType.UNDERGRADUATE,
    )

    # 将 session 缓存到 account 的 session_manager 中
    session_mgr = account.session_manager
    session_name = "webvpn" if use_webvpn else "direct"
    # SessionManager 的 get_session 会优先读取 instances[name]，
    # 这里直接放入已登录 session，避免再次实例化登录类导致缺参错误。
    session_mgr.sessions[session_name] = lambda: session
    session_mgr.instances[session_name] = session

    account.password = account.password  # 保持密码不变
    return session


def get_logged_in_session(
    account: Account,
    session_name: str = "direct",
    login_url: str = JWXT_LOGIN_URL,
    use_webvpn: bool = False,
) -> object:
    """
    获取已登录 session，若不可用则执行登录。
    返回 session 对象。
    """
    try:
        session = account.session_manager.get_session(session_name)
        # 简单验证 session 是否可用
        if session is not None:
            return session
    except (ValueError, KeyError):
        pass

    # 需要登录
    login_and_get_session(account, login_url, use_webvpn)

    try:
        return account.session_manager.get_session(session_name)
    except (ValueError, KeyError):
        # 如果直接的 session 名不存在，尝试查找
        instances = account.session_manager.instances
        for name, sess in instances.items():
            if sess is not None:
                return sess
        raise RuntimeError("登录失败，无法获取 session")


def get_logged_in_attendance_session(
    account: Account,
    session_name: str = "attendance_direct",
    use_webvpn: bool = False,
) -> object:
    """
    获取已登录的考勤系统 session，若不可用则执行考勤专用登录。
    """
    try:
        session = account.session_manager.get_session(session_name)
        if session is not None:
            return session
    except (ValueError, KeyError):
        pass

    from attendance.attendance import AttendanceNewLogin, AttendanceNewWebVPNLogin

    is_postgraduate = (account.type == Account.AccountType.POSTGRADUATE)
    session = get_session(fit_system=True)
    visitor_id = str(cfg.loginId.value)

    if use_webvpn:
        # WebVPN 登录分两步：先登录 WebVPN，再登录考勤系统。
        vpn_login = NewLogin(WEBVPN_LOGIN_URL, session, visitor_id=visitor_id)
        vpn_login.login_or_raise(account.username, account.password)
        attendance_login = AttendanceNewWebVPNLogin(session, is_postgraduate=is_postgraduate, visitor_id=visitor_id)
    else:
        attendance_login = AttendanceNewLogin(session, is_postgraduate=is_postgraduate, visitor_id=visitor_id)

    attendance_login.login_or_raise(account.username, account.password)

    account.session_manager.sessions[session_name] = lambda: session
    account.session_manager.instances[session_name] = session
    return session
