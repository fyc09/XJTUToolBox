from __future__ import annotations

import base64
import copy
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator
from urllib.parse import urlparse

from auth import (
    GMIS_LOGIN_URL,
    JWXT_LOGIN_URL,
    LMS_LOGIN_URL,
    LoginState,
    NewLogin,
    ServerError,
)
from gmis.score import GraduateScore
from jwxt.schedule import Schedule
from jwxt.score import Score
from xjtutoolbox.contracts.data import (
    AccountInvalid,
    AccountInfo,
    AppError,
    AuthenticationError,
    Challenge,
    ChallengeAnswer,
    InputRequired,
    ProtocolError,
)
from xjtutoolbox.infrastructure.http import CampusSession, DownloadStream
from xjtutoolbox.infrastructure.storage import AccountStore, DownloadFile


@dataclass
class _Attempt:
    login: NewLogin
    challenge: Challenge
    expires: float


class CampusAPI:
    """Account-bound protocol and storage operations. No task/progress API.

    Existing pure protocol parsers are retained. Live sessions, login objects
    and responses stay behind this boundary; callers receive snapshots only.
    """

    def __init__(
        self,
        store: AccountStore,
        session_factory: Callable = CampusSession,
        login_factory: Callable = NewLogin,
    ):
        self.store = store
        self._session_factory, self._login_factory = session_factory, login_factory
        self._lock = threading.RLock()
        self._sessions = {}
        self._users = {}
        self._authenticated = set()
        self._attempts: dict[tuple[str, str], _Attempt] = {}
        self._closed = False

    def list_accounts(self) -> tuple[AccountInfo, ...]:
        return self.store.list()

    def add_account(
        self, username: str, password: str, nickname: str, kind: str, remember: bool
    ) -> AccountInfo:
        return self.store.add(username, password, nickname, kind, remember)

    def set_password(self, account_id: str, password: str) -> None:
        self.store.set_password(account_id, password)

    def account(self, account_id: str) -> AccountInfo:
        return self.store.get(account_id)

    def remove_account(self, account_id: str) -> None:
        self.store.remove(account_id)
        # Active users clean up at the end of their lease. No live session is
        # closed while requests still owns it.
        with self._lock:
            keys = [key for key in self._sessions if key[0] == account_id]
            for key in keys:
                self._authenticated.discard(key)
                self._attempts.pop(key, None)
            if not self._users.get(account_id, 0):
                self._close_account(account_id)

    @contextmanager
    def account_scope(self, account_id: str) -> Iterator[None]:
        with self.store.scope(account_id):
            with self._lock:
                self._users[account_id] = self._users.get(account_id, 0) + 1
            try:
                yield
            finally:
                with self._lock:
                    self._users[account_id] -= 1
                try:
                    self.store.get(account_id)
                except AccountInvalid:
                    self._close_account(account_id)

    def assert_valid(self, account_id: str) -> None:
        self.store.get(account_id)

    def setting(self, key: str, default: str) -> str:
        return self.store.setting(key, default)

    def save_setting(self, key: str, value: str) -> None:
        self.store.save_setting(key, value)

    def _session(self, account_id, site):
        self.store.get(account_id)
        with self._lock:
            if self._closed:
                raise AppError("应用正在退出")
            key = (account_id, site)
            if key not in self._sessions:
                self._sessions[key] = self._session_factory()
            return self._sessions[key]

    def authenticate(
        self, account_id: str, site: str, answer: ChallengeAnswer | None = None
    ) -> None:
        """Authenticate or return an account-bound, expiring input challenge."""
        account = self.store.get(account_id)
        key = (account_id, site)
        session = self._session(account_id, site)
        try:
            session.authenticating = True
            if key in self._authenticated and answer is None:
                return
            attempt = self._attempts.get(key)
            if attempt is not None and time.monotonic() >= attempt.expires:
                self._attempts.pop(key, None)
                attempt = None
            if answer is not None:
                if (
                    attempt is None
                    or answer.challenge_id != attempt.challenge.challenge_id
                ):
                    raise AuthenticationError("验证已失效或不属于此账户，请重新查询")
                login = attempt.login
                if attempt.challenge.kind == "mfa":
                    login.mfa_context.verify_phone_code(answer.value)
                    state, detail = login.login()
                else:
                    state, detail = login.login(jcaptcha=answer.value)
                self._attempts.pop(key, None)
            elif attempt is not None:
                raise InputRequired(attempt.challenge)
            else:
                urls = {
                    "jwxt": JWXT_LOGIN_URL,
                    "gmis": GMIS_LOGIN_URL,
                    "lms": LMS_LOGIN_URL,
                }
                url = urls[site]
                if not url.startswith(("https://", "http://")):
                    url = "https://" + url
                login = self._login_factory(url, session=session)
                kind = (
                    NewLogin.POSTGRADUATE
                    if account.kind == "postgraduate"
                    else NewLogin.UNDERGRADUATE
                )
                state, detail = login.login(
                    account.username, self.store.password(account_id), account_type=kind
                )
            if state == LoginState.REQUIRE_ACCOUNT_CHOICE:
                kind = (
                    NewLogin.POSTGRADUATE
                    if account.kind == "postgraduate"
                    else NewLogin.UNDERGRADUATE
                )
                state, detail = login.login(account_type=kind)
            if state in (LoginState.REQUIRE_MFA, LoginState.REQUIRE_CAPTCHA):
                image = ""
                if state == LoginState.REQUIRE_MFA:
                    detail.send_verify_code()
                    prompt, kind = "请输入手机验证码", "mfa"
                else:
                    image = base64.b64encode(login.getJCaptchaCode()).decode("ascii")
                    prompt, kind = "请输入图片验证码", "captcha"
                challenge = Challenge(
                    secrets.token_urlsafe(24), account_id, site, kind, prompt, image
                )
                self._attempts[key] = _Attempt(login, challenge, time.monotonic() + 300)
                raise InputRequired(challenge)
            if state != LoginState.SUCCESS:
                raise AuthenticationError("登录失败，请核对账户和密码")
            self.store.get(account_id)
            self._authenticated.add(key)
        except ServerError as exc:
            raise AuthenticationError("认证接口拒绝验证，请重新查询") from exc
        finally:
            session.authenticating = False

    def _query(self, account_id, site, operation):
        try:
            result = operation(self._session(account_id, site))
            self.store.get(account_id)
            return copy.deepcopy(result)
        except AuthenticationError:
            self._authenticated.discard((account_id, site))
            raise
        except ServerError as exc:
            if exc.code == 102:
                self._authenticated.discard((account_id, site))
                raise AuthenticationError("校园系统要求重新认证") from exc
            raise AppError("校园系统拒绝查询，请检查学校系统状态") from exc
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ProtocolError("校园系统返回的数据格式不符合预期") from exc

    def current_term(self, account_id: str) -> str:
        return self._query(
            account_id, "jwxt", lambda session: Schedule(session).termString
        )

    def scores(
        self, account_id: str, terms: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        account = self.store.get(account_id)
        if account.kind == "postgraduate":
            return self._query(
                account_id, "gmis", lambda session: GraduateScore(session).grade()
            )
        return self._query(
            account_id,
            "jwxt",
            lambda session: Score(session).grade(
                list(terms) if terms else None, jwapp_format=True
            ),
        )

    def reported_scores(
        self, account_id: str, terms: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        account = self.store.get(account_id)
        return self._query(
            account_id,
            "jwxt",
            lambda session: Score(session).reported_grade(
                account.username, list(terms) if terms else None
            ),
        )

    @contextmanager
    def open_download(self, account_id: str, url: str) -> Iterator[DownloadStream]:
        parts = urlparse(url)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise AppError("下载地址必须是有效的 HTTPS 地址")
        try:
            response = self._session(account_id, "lms").get(
                url, stream=True, headers={"Accept-Encoding": "identity"}
            )
            with DownloadStream(response) as stream:
                yield stream
        except AuthenticationError:
            self._authenticated.discard((account_id, "lms"))
            raise

    def prepare_download(self, account_id: str, destination: str) -> DownloadFile:
        self.store.get(account_id)
        return DownloadFile(
            destination, lambda action: self.store.commit(account_id, action)
        )

    def _close_account(self, account_id):
        with self._lock:
            for key in [k for k in self._sessions if k[0] == account_id]:
                self._sessions.pop(key).close()
                self._authenticated.discard(key)
                self._attempts.pop(key, None)

    def close(self) -> None:
        """Call only after the entrypoint has joined all active operations."""
        with self._lock:
            self._closed = True
            for session in self._sessions.values():
                session.close()
            self._sessions.clear()
            self._attempts.clear()
            self._authenticated.clear()
