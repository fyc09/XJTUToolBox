"""
账户管理 CLI 命令
"""

from cli.output import print_output, print_error, print_success
from cli.session import get_account_manager
from shared.account import Account
from shared.config import cfg


def cmd_list(use_json: bool = False):
    """列出所有账户。"""
    mgr = get_account_manager()
    if not mgr.accounts:
        print_error("没有已保存的账户。", use_json)
        return

    accounts_data = []
    for acct in mgr.accounts:
        is_current = (acct is mgr.current)
        info = {
            "uuid": acct.uuid,
            "username": acct.username,
            "nickname": acct.nickname or "",
            "type": "本科生" if acct.type == Account.AccountType.UNDERGRADUATE else "研究生",
            "is_current": is_current,
            "has_avatar": acct.avatar_exists(),
        }
        accounts_data.append(info)

    print_output(accounts_data, use_json, title="账户列表")


def cmd_switch(uuid: str, use_json: bool = False):
    """切换当前账户。"""
    mgr = get_account_manager()
    for acct in mgr.accounts:
        if acct.uuid == uuid:
            mgr.current = acct
            mgr.save_suitable()
            print_success(f"已切换到账户: {acct.nickname or acct.username}", acct.to_diction(), use_json)
            return
    print_error(f"未找到 uuid 为 {uuid} 的账户。使用 `xjtutoolbox account list` 查看。", use_json)


def cmd_remove(uuid: str, use_json: bool = False):
    """删除账户。"""
    mgr = get_account_manager()
    for acct in mgr.accounts:
        if acct.uuid == uuid:
            mgr.remove(acct)
            mgr.save_suitable()
            print_success(f"已删除账户: {acct.nickname or acct.username}", use_json=use_json)
            return
    print_error(f"未找到 uuid 为 {uuid} 的账户。", use_json)


def cmd_set_encrypted(enable: bool, password: str = None, use_json: bool = False):
    """设置/取消账户加密。"""
    mgr = get_account_manager()
    if enable:
        if not password:
            print_error("启用加密需要提供 --password 参数。", use_json)
            return
        key = password.encode("utf-8")
        mgr.setEncrypted(True, key=key, use_keyring=cfg.useKeyring.value)
        print_success("账户已启用加密。", use_json=use_json)
    else:
        if password:
            try:
                key = password.encode("utf-8")
                mgr.setEncrypted(False, key=key, use_keyring=cfg.useKeyring.value)
                print_success("账户已取消加密。", use_json=use_json)
            except ValueError as e:
                print_error(f"解密失败: {e}", use_json)
        else:
            mgr.setEncrypted(False, use_keyring=cfg.useKeyring.value)
            print_success("账户已取消加密。", use_json=use_json)
