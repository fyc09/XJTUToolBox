import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TEST_DOMAIN = "qt-ui"

from app.threads.LMSFileDownloadThread import LMSFileDownloadThread
from app.threads.ScoreThread import ScoreThread
from test.refactor.test_protocol import StreamingResponse
from xjtutoolbox.contracts.data import ScoreResult


class LegacyAdapterTest(unittest.TestCase):
    def test_score_thread_calls_shared_service_and_emits_one_success(self):
        thread = ScoreThread(["2025-2026-1"])
        account = SimpleNamespace(uuid="a", username="student")
        rows = [{"courseName": "数学", "score": 0}]
        results, finished = [], []
        thread.scores.connect(lambda values, pg: results.append((values, pg)))
        thread.hasFinished.connect(lambda: finished.append(True))
        with (
            patch("app.threads.ScoreThread.accounts", SimpleNamespace(current=account)),
            patch(
                "app.utils.legacy_academic.AcademicService.query_scores",
                return_value=ScoreResult("a", False, tuple(rows)),
            ) as service,
        ):
            thread.run()
        self.assertEqual(("2025-2026-1",), service.call_args.args[0].terms)
        self.assertEqual([(rows, False)], results)
        self.assertEqual([True], finished)

    def test_old_download_uses_atomic_shared_service(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "file"
            target.write_bytes(b"old")
            response = StreamingResponse()
            session = Mock()
            session.get.return_value = response
            thread = LMSFileDownloadThread(
                session, "https://lms.xjtu.edu.cn/file", str(target), "file"
            )
            finished = []
            thread.hasFinished.connect(lambda: finished.append(True))
            thread.run()
            self.assertEqual(b"onetwo", target.read_bytes())
            self.assertEqual([True], finished)
            self.assertTrue(response.closed)

    def test_cancel_old_download_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "file"
            target.write_bytes(b"old")
            response = StreamingResponse()
            session = Mock()
            session.get.return_value = response
            thread = LMSFileDownloadThread(
                session, "https://lms.xjtu.edu.cn/file", str(target), "file"
            )
            cancelled = []
            thread.canceled.connect(lambda: cancelled.append(True))
            thread.progressChanged.connect(
                lambda amount: setattr(thread, "can_run", False)
            )
            thread.run()
            self.assertEqual(b"old", target.read_bytes())
            self.assertEqual([True], cancelled)
            self.assertTrue(response.closed)
            self.assertEqual([], list(Path(directory).glob(".xjtu-download-*")))

    def test_incomplete_old_download_has_one_failure_and_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "file"
            target.write_bytes(b"old")
            response = StreamingResponse(length="100")
            session = Mock()
            session.get.return_value = response
            thread = LMSFileDownloadThread(
                session, "https://lms.xjtu.edu.cn/file", str(target), "file"
            )
            errors, cancelled, finished = [], [], []
            thread.error.connect(lambda *args: errors.append(args))
            thread.canceled.connect(lambda: cancelled.append(True))
            thread.hasFinished.connect(lambda: finished.append(True))
            thread.run()
            self.assertEqual(b"old", target.read_bytes())
            self.assertEqual(1, len(errors))
            self.assertEqual([True], cancelled)
            self.assertEqual([], finished)
