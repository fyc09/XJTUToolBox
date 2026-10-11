import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

TEST_DOMAIN = "core"

from auth import LoginState
from xjtutoolbox.api import CampusAPI
from xjtutoolbox.contracts.data import (
    AuthenticationError,
    ChallengeAnswer,
    InputRequired,
    NetworkError,
    ProtocolError,
)
from xjtutoolbox.infrastructure.http import CampusSession, DownloadStream
from xjtutoolbox.infrastructure.storage import AccountStore


class StreamingResponse:
    def __init__(
        self,
        content_type="application/octet-stream",
        length="6",
        content=(b"one", b"two"),
    ):
        self.url = "https://lms.xjtu.edu.cn/file"
        self.headers = {"Content-Type": content_type, "Content-Length": length}
        self.content = content
        self.closed = False

    @property
    def text(self):
        raise AssertionError("streamed response was eagerly read")

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield from self.content

    def close(self):
        self.closed = True


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = AccountStore(Path(self.temporary.name))
        self.account = self.store.add("a", "secret", "a", "undergraduate", False)
        self.other = self.store.add("b", "secret", "b", "undergraduate", False)
        self.login = Mock()
        self.login_factory = Mock(return_value=self.login)
        self.api = CampusAPI(
            self.store, session_factory=Mock, login_factory=self.login_factory
        )
        self.addCleanup(self.api.close)

    def test_streamed_unknown_mime_never_reads_text(self):
        response = StreamingResponse("")
        with patch("requests.Session.request", return_value=response):
            actual = CampusSession().get(response.url, stream=True)
        self.assertIs(response, actual)

    def test_streamed_plaintext_never_reads_whole_text(self):
        response = StreamingResponse("text/plain")
        with patch("requests.Session.request", return_value=response):
            actual = CampusSession().get(response.url, stream=True)
        with DownloadStream(actual) as stream:
            self.assertEqual([b"one", b"two"], list(stream.chunks()))
        self.assertTrue(response.closed)

    def test_streamed_login_page_fails_from_bounded_first_chunk(self):
        response = StreamingResponse(
            "text/html",
            content=(b'<form id="fm1"><input name="execution"></form>', b"unread"),
        )
        with self.assertRaises(AuthenticationError), DownloadStream(response) as stream:
            list(stream.chunks())
        self.assertTrue(response.closed)

    def test_streamed_redirect_to_cas_closes_response(self):
        response = StreamingResponse()
        response.url = "https://login.xjtu.edu.cn/cas/login"
        with (
            patch("requests.Session.request", return_value=response),
            self.assertRaises(AuthenticationError),
        ):
            CampusSession().get("https://lms.xjtu.edu.cn/file", stream=True)
        self.assertTrue(response.closed)

    def test_fragmented_login_markup_is_detected_without_eager_read(self):
        response = StreamingResponse(
            "text/html",
            content=(b'<form id="fm', b'1"><input name="exec', b'ution"></form>'),
        )
        with self.assertRaises(AuthenticationError), DownloadStream(response) as stream:
            list(stream.chunks())
        self.assertTrue(response.closed)

    def test_stream_uses_available_bytes_so_cancel_can_run_between_reads(self):
        response = StreamingResponse()
        response.raw = Mock()
        response.raw.read1.side_effect = [b"a", b"b", b""]
        with DownloadStream(response) as stream:
            self.assertEqual([b"a", b"b"], list(stream.chunks()))
        self.assertEqual(3, response.raw.read1.call_count)

    def test_http_error_is_classified_without_response_body(self):
        import requests

        response = StreamingResponse()
        response.raise_for_status = Mock(
            side_effect=requests.HTTPError("secret-bearing-url", response=response)
        )
        with (
            patch("requests.Session.request", return_value=response),
            self.assertRaises(NetworkError) as caught,
        ):
            CampusSession().get(response.url, stream=True)
        self.assertNotIn("secret", str(caught.exception))
        self.assertTrue(response.closed)

    def test_default_io_timeout_is_explicit(self):
        response = StreamingResponse()
        with patch("requests.Session.request", return_value=response) as request:
            CampusSession().get(response.url, stream=True)
        self.assertEqual((10, 30), request.call_args.kwargs["timeout"])

    def test_encoded_length_is_not_used_as_decoded_progress_total(self):
        response = StreamingResponse()
        response.headers["Content-Encoding"] = "gzip"
        with DownloadStream(response) as stream:
            self.assertIsNone(stream.length)

    def test_mfa_challenge_is_data_and_send_code_is_not_repeated(self):
        context = Mock()
        self.login.mfa_context = context
        self.login.login.side_effect = [
            (LoginState.REQUIRE_MFA, context),
            (LoginState.SUCCESS, None),
        ]
        with self.assertRaises(InputRequired) as raised:
            self.api.authenticate(self.account.account_id, "jwxt")
        challenge = raised.exception.challenge
        self.assertEqual(self.account.account_id, challenge.account_id)
        self.assertFalse(hasattr(challenge, "session"))
        with self.assertRaises(InputRequired):
            self.api.authenticate(self.account.account_id, "jwxt")
        context.send_verify_code.assert_called_once()
        self.api.authenticate(
            self.account.account_id,
            "jwxt",
            ChallengeAnswer(challenge.challenge_id, "123456"),
        )
        context.verify_phone_code.assert_called_once_with("123456")

    def test_challenge_cannot_be_replayed_on_another_account(self):
        self.login.login.return_value = (LoginState.REQUIRE_MFA, Mock())
        with self.assertRaises(InputRequired) as raised:
            self.api.authenticate(self.account.account_id, "jwxt")
        with self.assertRaises(AuthenticationError):
            self.api.authenticate(
                self.other.account_id,
                "jwxt",
                ChallengeAnswer(raised.exception.challenge.challenge_id, "123"),
            )
        self.login.mfa_context.verify_phone_code.assert_not_called()

    def test_expired_challenge_cannot_resume(self):
        self.login.login.return_value = (LoginState.REQUIRE_MFA, Mock())
        with (
            patch("xjtutoolbox.api.campus.time.monotonic", return_value=0),
            self.assertRaises(InputRequired) as raised,
        ):
            self.api.authenticate(self.account.account_id, "jwxt")
        with (
            patch("xjtutoolbox.api.campus.time.monotonic", return_value=301),
            self.assertRaises(AuthenticationError),
        ):
            self.api.authenticate(
                self.account.account_id,
                "jwxt",
                ChallengeAnswer(raised.exception.challenge.challenge_id, "123"),
            )

    def test_captcha_image_is_not_a_live_login_object(self):
        self.login.login.side_effect = [
            (LoginState.REQUIRE_CAPTCHA, None),
            (LoginState.SUCCESS, None),
        ]
        self.login.getJCaptchaCode.return_value = b"image"
        with self.assertRaises(InputRequired) as raised:
            self.api.authenticate(self.account.account_id, "jwxt")
        self.assertEqual("aW1hZ2U=", raised.exception.challenge.image_base64)
        self.api.authenticate(
            self.account.account_id,
            "jwxt",
            ChallengeAnswer(raised.exception.challenge.challenge_id, "abc"),
        )
        self.assertEqual("abc", self.login.login.call_args.kwargs["jcaptcha"])

    def test_sessions_are_separate_for_different_accounts(self):
        self.login.login.return_value = (LoginState.SUCCESS, None)
        self.api.authenticate(self.account.account_id, "jwxt")
        self.api.authenticate(self.other.account_id, "jwxt")
        self.assertIsNot(
            self.login_factory.call_args_list[0].kwargs["session"],
            self.login_factory.call_args_list[1].kwargs["session"],
        )

    def test_parser_failure_becomes_protocol_error(self):
        with patch("xjtutoolbox.api.campus.Score") as factory:
            factory.return_value.grade.side_effect = KeyError("datas")
            with self.assertRaises(ProtocolError):
                self.api.scores(self.account.account_id, None)

    def test_auth_failure_invalidates_cached_login(self):
        self.login.login.return_value = (LoginState.SUCCESS, None)
        self.api.authenticate(self.account.account_id, "jwxt")
        with patch("xjtutoolbox.api.campus.Score") as factory:
            factory.return_value.grade.side_effect = AuthenticationError("expired")
            with self.assertRaises(AuthenticationError):
                self.api.scores(self.account.account_id, None)
        self.api.authenticate(self.account.account_id, "jwxt")
        self.assertEqual(2, self.login_factory.call_count)
