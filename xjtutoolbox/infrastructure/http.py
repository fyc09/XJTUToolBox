from __future__ import annotations

import requests
from urllib.parse import urlparse
from urllib3.exceptions import HTTPError as TransportError

from auth import is_safety_verify_page
from auth.util import generate_user_agent
from xjtutoolbox.contracts.data import AuthenticationError, NetworkError


class CampusSession(requests.Session):
    """Bounded I/O and auth detection without eagerly reading binary streams."""

    def __init__(self):
        super().__init__()
        self.headers["User-Agent"] = generate_user_agent()
        self.authenticating = False

    def request(self, method, url, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (10, 30)
        try:
            response = super().request(method, url, **kwargs)
            response.raise_for_status()
        except requests.RequestException as exc:
            if getattr(exc, "response", None) is not None:
                exc.response.close()
            raise NetworkError("校园系统连接失败或返回 HTTP 错误，请稍后重试") from exc
        inspect_body = not kwargs.get("stream")
        redirected_login = urlparse(response.url).hostname == "login.xjtu.edu.cn"
        if not self.authenticating and redirected_login:
            response.close()
            raise AuthenticationError("登录已失效，请重新查询并完成验证")
        if not self.authenticating and inspect_body:
            page = response.text
            if is_safety_verify_page(page) or (
                'id="fm1"' in page and 'name="execution"' in page
            ):
                response.close()
                raise AuthenticationError("登录已失效，请重新查询并完成验证")
        return response


class DownloadStream:
    def __init__(self, response):
        self._response = response
        length = response.headers.get("Content-Length", "")
        encoded = response.headers.get("Content-Encoding", "identity") != "identity"
        self.length = (
            int(length)
            if length.isdigit() and int(length) > 0 and not encoded
            else None
        )

    def __enter__(self):
        return self

    def chunks(self):
        try:
            raw = getattr(self._response, "raw", None)
            if raw is not None and hasattr(raw, "read1"):

                def available_chunks():
                    while chunk := raw.read1(64 * 1024, decode_content=True):
                        yield chunk

                chunks = available_chunks()
            else:
                chunks = self._response.iter_content(chunk_size=64 * 1024)
            content_type = self._response.headers.get("Content-Type", "").lower()
            preview = b""
            for chunk in chunks:
                if len(preview) < 64 * 1024:
                    preview += chunk[: 64 * 1024 - len(preview)]
                    if (
                        "html" in content_type
                        or "text" in content_type
                        or preview.lstrip().startswith(b"<")
                    ):
                        page = preview.decode("utf-8", errors="ignore")
                        if is_safety_verify_page(page) or (
                            'id="fm1"' in page and 'name="execution"' in page
                        ):
                            raise AuthenticationError(
                                "下载接口要求重新认证，请重新查询"
                            )
                yield chunk
        except (requests.RequestException, TransportError, OSError) as exc:
            raise NetworkError("下载连接中断") from exc

    def __exit__(self, *args):
        self._response.close()
