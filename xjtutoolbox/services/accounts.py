from __future__ import annotations

from xjtutoolbox.api import CampusAPI
from xjtutoolbox.contracts.data import AppError


class AccountService:
    def __init__(self, api: CampusAPI, cancel_account=lambda account_id: None):
        self._api, self._cancel_account = api, cancel_account

    def list_accounts(self):
        return self._api.list_accounts()

    def add(
        self, username, password, nickname="", kind="undergraduate", remember=False
    ):
        if not username.strip() or not password:
            raise AppError("用户名和密码不能为空")
        if kind not in ("undergraduate", "postgraduate"):
            raise AppError("账户类型无效")
        return self._api.add_account(
            username.strip(), password, nickname.strip(), kind, remember
        )

    def unlock(self, account_id, password):
        if not password:
            raise AppError("密码不能为空")
        self._api.set_password(account_id, password)

    def remove(self, account_id):
        self._api.remove_account(account_id)
        self._cancel_account(account_id)

    def color_mode(self):
        mode = self._api.setting("color_mode", "light")
        return mode if mode in ("light", "dark") else "light"

    def set_color_mode(self, mode):
        if mode not in ("light", "dark"):
            raise AppError("仅支持浅色或深色模式")
        self._api.save_setting("color_mode", mode)
