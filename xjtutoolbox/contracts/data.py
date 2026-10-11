from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AccountInfo:
    account_id: str
    username: str
    nickname: str
    kind: str = "undergraduate"


@dataclass(frozen=True)
class Challenge:
    challenge_id: str
    account_id: str
    site: str
    kind: str
    prompt: str
    image_base64: str = ""


@dataclass(frozen=True)
class ChallengeAnswer:
    challenge_id: str
    value: str


@dataclass(frozen=True)
class ScoreRequest:
    account_id: str
    terms: tuple[str, ...] | None = None
    current_term: bool = False
    include_report: bool = False
    answer: ChallengeAnswer | None = None


@dataclass(frozen=True)
class ScoreResult:
    account_id: str
    postgraduate: bool
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class DownloadRequest:
    account_id: str
    url: str
    destination: str
    answer: ChallengeAnswer | None = None


@dataclass(frozen=True)
class DownloadResult:
    account_id: str
    path: str
    bytes_written: int


class AppError(Exception):
    code = "business_error"


class AuthenticationError(AppError):
    code = "authentication_error"


class NetworkError(AppError):
    code = "network_error"


class ProtocolError(AppError):
    code = "protocol_error"


class AccountInvalid(AppError):
    code = "account_invalid"


class InputRequired(AppError):
    code = "input_required"

    def __init__(self, challenge: Challenge):
        super().__init__(challenge.prompt)
        self.challenge = challenge


class Cancelled(AppError):
    code = "cancelled"

    def __init__(self, message: str = "操作已取消", partial_result: Any = None):
        super().__init__(message)
        self.partial_result = partial_result


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    challenge: Challenge | None = None

    @classmethod
    def from_exception(cls, error: BaseException) -> ErrorInfo:
        if isinstance(error, InputRequired):
            return cls(error.code, str(error), error.challenge)
        if isinstance(error, AppError):
            return cls(error.code, str(error))
        # Unexpected library exceptions can contain credential-bearing URLs.
        return cls("internal_error", "操作失败，请查看开发日志或报告此问题")
