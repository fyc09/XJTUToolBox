import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

TEST_DOMAIN = "core"

from xjtutoolbox.api import CampusAPI
from xjtutoolbox.contracts.data import (
    AccountInvalid,
    AppError,
    Cancelled,
    DownloadRequest,
    ProtocolError,
    ScoreRequest,
)
from xjtutoolbox.contracts.tasks import NullContext
from xjtutoolbox.infrastructure.storage import AccountStore
from xjtutoolbox.services import AccountService, AcademicService, DownloadService


class FixtureAPI(CampusAPI):
    def __init__(self, directory):
        super().__init__(AccountStore(directory))
        self.calls = []
        self.score_rows = [
            {"courseName": "高等数学", "score": 0, "coursePoint": 4, "gpa": 0}
        ]
        self.report_rows = []
        self.content = [b"one", b"two"]
        self.length = 6
        self.closed_stream = False

    def authenticate(self, account_id, site, answer=None):
        self.assert_valid(account_id)
        self.calls.append(("auth", account_id, site))

    def current_term(self, account_id):
        self.calls.append(("term", account_id))
        return "2025-2026-1"

    def scores(self, account_id, terms):
        self.calls.append(("scores", account_id, terms))
        return [dict(row) for row in self.score_rows]

    def reported_scores(self, account_id, terms):
        return [dict(row) for row in self.report_rows]

    @contextmanager
    def open_download(self, account_id, url):
        api = self

        class Stream:
            length = api.length

            def chunks(self):
                yield from api.content

        try:
            yield Stream()
        finally:
            self.closed_stream = True


class RecordingContext(NullContext):
    def __init__(self):
        self.events, self.cancelled = [], False

    def report(self, event):
        self.events.append(event)

    def check_cancelled(self):
        if self.cancelled:
            raise Cancelled()


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.api = FixtureAPI(self.directory)
        self.addCleanup(self.api.close)
        self.accounts = AccountService(self.api)
        self.account = self.accounts.add("student", "secret")
        self.academic = AcademicService(self.api)
        self.downloads = DownloadService(self.api)
        self.context = RecordingContext()

    def test_current_term_and_zero_score_are_preserved(self):
        result = self.academic.query_scores(
            ScoreRequest(self.account.account_id, current_term=True), self.context
        )
        self.assertEqual(0, result.rows[0]["score"])
        self.assertEqual(
            ("scores", self.account.account_id, ("2025-2026-1",)), self.api.calls[-1]
        )
        self.assertEqual(
            ["authenticate", "term", "scores"], [p.stage for p in self.context.events]
        )
        self.assertTrue(all(p.overall is None for p in self.context.events))

    def test_report_merge_deduplicates_new_report_rows(self):
        self.api.report_rows = [
            {"courseName": "高等数学"},
            {"courseName": "线性代数"},
            {"courseName": "线性代数"},
        ]
        result = self.academic.query_scores(
            ScoreRequest(self.account.account_id, include_report=True), self.context
        )
        self.assertEqual(
            ["高等数学", "线性代数"], [r["courseName"] for r in result.rows]
        )

    def test_result_is_a_snapshot_not_api_owned_collection(self):
        result = self.academic.query_scores(
            ScoreRequest(self.account.account_id), self.context
        )
        result.rows[0]["courseName"] = "changed"
        self.assertEqual("高等数学", self.api.score_rows[0]["courseName"])

    def test_invalid_term_never_authenticates(self):
        with self.assertRaises(AppError):
            self.academic.query_scores(
                ScoreRequest(self.account.account_id, terms=("bad",)), self.context
            )
        self.assertEqual([], self.api.calls)

    def test_incompatible_term_options_never_authenticate(self):
        with self.assertRaises(AppError):
            self.academic.query_scores(
                ScoreRequest(
                    self.account.account_id, terms=("2025-2026-1",), current_term=True
                ),
                self.context,
            )

    def test_postgraduate_uses_own_site(self):
        account = self.accounts.add("pg", "secret", kind="postgraduate")
        result = self.academic.query_scores(
            ScoreRequest(account.account_id), self.context
        )
        self.assertTrue(result.postgraduate)
        self.assertEqual(("auth", account.account_id, "gmis"), self.api.calls[0])

    def test_unsupported_postgraduate_filter_is_explicit(self):
        account = self.accounts.add("pg", "secret", kind="postgraduate")
        with self.assertRaises(AppError):
            self.academic.query_scores(
                ScoreRequest(account.account_id, current_term=True), self.context
            )
        self.assertEqual([], self.api.calls)

    def test_account_deleted_during_query_cannot_return_success(self):
        original = self.api.scores

        def deleting(account_id, terms):
            result = original(account_id, terms)
            with patch("keyring.get_password", return_value=None):
                self.accounts.remove(account_id)
            return result

        self.api.scores = deleting
        with self.assertRaises(AccountInvalid):
            self.academic.query_scores(
                ScoreRequest(self.account.account_id), self.context
            )

    def test_cancellation_after_auth_skips_query(self):
        def authenticate(*args):
            self.context.cancelled = True

        self.api.authenticate = authenticate
        with self.assertRaises(Cancelled):
            self.academic.query_scores(
                ScoreRequest(self.account.account_id), self.context
            )
        self.assertEqual([], self.api.calls)

    def test_stage_failure_skips_later_report(self):
        def fail(*args):
            raise ProtocolError("bad response")

        self.api.scores = fail
        with self.assertRaises(ProtocolError):
            self.academic.query_scores(
                ScoreRequest(self.account.account_id, include_report=True), self.context
            )
        self.assertEqual(
            ["authenticate", "scores"], [p.stage for p in self.context.events]
        )

    def test_download_is_atomic_and_closes_stream(self):
        target = self.directory / "existing.bin"
        target.write_bytes(b"old")
        result = self.downloads.download(
            DownloadRequest(
                self.account.account_id, "https://lms.xjtu.edu.cn/file", str(target)
            ),
            self.context,
        )
        self.assertEqual(b"onetwo", target.read_bytes())
        self.assertEqual(6, result.bytes_written)
        self.assertTrue(self.api.closed_stream)
        self.assertEqual([], list(self.directory.glob(".xjtu-download-*")))

    def test_cancelled_download_preserves_previous_file(self):
        target = self.directory / "existing.bin"
        target.write_bytes(b"old")

        def report(event):
            self.context.events.append(event)
            if event.stage == "download" and event.completed:
                self.context.cancelled = True

        self.context.report = report
        with self.assertRaises(Cancelled):
            self.downloads.download(
                DownloadRequest(self.account.account_id, "url", str(target)),
                self.context,
            )
        self.assertEqual(b"old", target.read_bytes())
        self.assertTrue(self.api.closed_stream)
        self.assertEqual([], list(self.directory.glob(".xjtu-download-*")))

    def test_truncated_download_preserves_previous_file(self):
        target = self.directory / "existing.bin"
        target.write_bytes(b"old")
        self.api.length = 100
        with self.assertRaises(ProtocolError):
            self.downloads.download(
                DownloadRequest(self.account.account_id, "url", str(target)),
                self.context,
            )
        self.assertEqual(b"old", target.read_bytes())
        self.assertTrue(self.api.closed_stream)

    def test_unknown_download_size_has_no_fabricated_total(self):
        self.api.length = None
        self.downloads.download(
            DownloadRequest(
                self.account.account_id, "url", str(self.directory / "new")
            ),
            self.context,
        )
        self.assertTrue(all(e.total is None for e in self.context.events))

    def test_account_removed_before_download_commit_cannot_replace_file(self):
        target = self.directory / "existing.bin"
        target.write_bytes(b"old")

        def chunks():
            yield b"one"
            with patch("keyring.get_password", return_value=None):
                self.accounts.remove(self.account.account_id)

        self.api.content = chunks()
        self.api.length = None
        with self.assertRaises(AccountInvalid):
            self.downloads.download(
                DownloadRequest(self.account.account_id, "url", str(target)),
                self.context,
            )
        self.assertEqual(b"old", target.read_bytes())
        self.assertEqual([], list(self.directory.glob(".xjtu-download-*")))

    def test_empty_destination_has_no_network_side_effect(self):
        with self.assertRaises(AppError):
            self.downloads.download(
                DownloadRequest(self.account.account_id, "url", ""), self.context
            )
        self.assertEqual([], self.api.calls)

    def test_password_is_not_written_into_metadata_database(self):
        self.assertNotIn(b"secret", self.api.store.path.read_bytes())

    def test_keyring_failure_does_not_create_half_account(self):
        with (
            patch("keyring.set_password", side_effect=RuntimeError("failed")),
            self.assertRaises(AppError),
        ):
            self.accounts.add("new", "secret", remember=True)
        self.assertEqual(1, len(self.accounts.list_accounts()))

    def test_account_recreation_does_not_reuse_identity(self):
        with patch("keyring.get_password", return_value=None):
            self.accounts.remove(self.account.account_id)
        new = self.accounts.add("student", "secret")
        self.assertNotEqual(self.account.account_id, new.account_id)
        with self.assertRaises(AccountInvalid):
            self.api.assert_valid(self.account.account_id)

    def test_settings_only_offer_light_and_dark_and_persist(self):
        self.accounts.set_color_mode("dark")
        self.assertEqual(
            "dark", AccountService(CampusAPI(AccountStore(self.directory))).color_mode()
        )
        with self.assertRaises(AppError):
            self.accounts.set_color_mode("material")

    def test_same_account_scope_serializes_whole_operations(self):
        entered, release, waiting = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        seen = []

        def first():
            with self.api.account_scope(self.account.account_id):
                seen.append("first-enter")
                entered.set()
                release.wait(2)
                seen.append("first-exit")

        def second():
            waiting.set()
            with self.api.account_scope(self.account.account_id):
                seen.append("second-enter")

        a = threading.Thread(target=first)
        a.start()
        self.assertTrue(entered.wait(2))
        b = threading.Thread(target=second)
        b.start()
        self.assertTrue(waiting.wait(2))
        release.set()
        a.join(2)
        b.join(2)
        self.assertEqual(["first-enter", "first-exit", "second-enter"], seen)
