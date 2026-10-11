from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import keyring

from xjtutoolbox.contracts.data import (
    AccountInfo,
    AccountInvalid,
    AppError,
    AuthenticationError,
)


class AccountStore:
    """Metadata in SQLite, remembered passwords in the system keyring.

    Deletion and result/file commits share a lock. Network calls hold a
    separate per-account lock, so deleting an account never waits on I/O.
    """

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._leases: dict[str, threading.RLock] = {}
        self._passwords: dict[str, str] = {}
        self._removed: set[str] = set()
        self.path = directory / "accounts-v2.sqlite3"
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, username TEXT, nickname TEXT, kind TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
            )

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self) -> tuple[AccountInfo, ...]:
        with self._lock, self._connect() as db:
            return tuple(
                AccountInfo(*row)
                for row in db.execute(
                    "SELECT id, username, nickname, kind FROM accounts ORDER BY rowid"
                )
            )

    def get(self, account_id: str) -> AccountInfo:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT id, username, nickname, kind FROM accounts WHERE id=?",
                (account_id,),
            ).fetchone()
            if row is None or account_id in self._removed:
                raise AccountInvalid("账户已删除或不存在")
            return AccountInfo(*row)

    def add(
        self, username: str, password: str, nickname: str, kind: str, remember: bool
    ) -> AccountInfo:
        account = AccountInfo(str(uuid4()), username, nickname or username, kind)
        with self._lock:
            if remember:
                try:
                    keyring.set_password("XJTUToolBox-v2", account.account_id, password)
                except Exception as exc:
                    raise AppError("系统凭据存储不可用，请取消记住密码后重试") from exc
            try:
                with self._connect() as db:
                    db.execute(
                        "INSERT INTO accounts VALUES (?, ?, ?, ?)",
                        (account.account_id, username, account.nickname, kind),
                    )
            except Exception:
                if remember:
                    keyring.delete_password("XJTUToolBox-v2", account.account_id)
                raise
            self._passwords[account.account_id] = password
        return account

    def set_password(self, account_id: str, password: str) -> None:
        with self._lock:
            self.get(account_id)
            self._passwords[account_id] = password

    def password(self, account_id: str) -> str:
        with self._lock:
            self.get(account_id)
            password = self._passwords.get(account_id)
            if password is None:
                try:
                    password = keyring.get_password("XJTUToolBox-v2", account_id)
                except Exception:
                    password = None
            if not password:
                raise AuthenticationError("请为此账户输入密码；密码不会写入账户数据库")
            return password

    def remove(self, account_id: str) -> None:
        with self._lock:
            self.get(account_id)
            # Credential cleanup failure leaves the account active and retryable.
            try:
                if keyring.get_password("XJTUToolBox-v2", account_id) is not None:
                    keyring.delete_password("XJTUToolBox-v2", account_id)
            except keyring.errors.NoKeyringError:
                pass
            except Exception as exc:
                raise AppError("无法清理系统凭据，请重试删除账户") from exc
            with self._connect() as db:
                db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            self._removed.add(account_id)
            self._passwords.pop(account_id, None)

    @contextmanager
    def scope(self, account_id: str):
        with self._lock:
            self.get(account_id)
            lock = self._leases.setdefault(account_id, threading.RLock())
        if not lock.acquire(timeout=30):
            raise AppError("此账户正在执行其他操作，请稍后重试")
        try:
            self.get(account_id)
            yield
        finally:
            lock.release()

    def commit(self, account_id: str, action):
        with self._lock:
            self.get(account_id)
            return action()

    def setting(self, key: str, default: str) -> str:
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            ).fetchone()
            return row[0] if row else default

    def save_setting(self, key: str, value: str) -> None:
        with self._lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))


class DownloadFile:
    def __init__(self, destination: str, commit):
        self.destination = Path(destination).expanduser().resolve()
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, path = tempfile.mkstemp(
            prefix=".xjtu-download-", dir=self.destination.parent
        )
        self.path = Path(path)
        self.file = os.fdopen(descriptor, "wb")
        self._commit = commit

    def __enter__(self):
        return self

    def write(self, chunk: bytes) -> None:
        self.file.write(chunk)

    def commit(self) -> str:
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()
        self._commit(lambda: os.replace(self.path, self.destination))
        return str(self.destination)

    def __exit__(self, *args):
        self.file.close()
        self.path.unlink(missing_ok=True)
