import tempfile
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

TEST_DOMAIN = "qt6-ui"

from PySide6.QtCore import QCoreApplication, QEvent, QThread, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle

from test.refactor.test_services import FixtureAPI
from xjtutoolbox.bootstrap import Application
from xjtutoolbox.gui.main import create_engine
from xjtutoolbox.runtime import TaskRegistry, TaskState
from xjtutoolbox.services import AccountService, AcademicService, DownloadService


APP = QGuiApplication.instance() or QGuiApplication([])


class QmlTest(unittest.TestCase):
    def test_real_gui_entrypoint_can_close_its_window_and_exit(self):
        program = """
import tempfile
from PySide6.QtCore import QTimer
import xjtutoolbox.gui.main as entry
original = entry.create_engine
def closing_engine(application, app):
    engine, model, bridge = original(application, app)
    QTimer.singleShot(50, model.requestClose)
    return engine, model, bridge
entry.create_engine = closing_engine
with tempfile.TemporaryDirectory() as directory:
    raise SystemExit(entry.main(['--data-dir', directory]))
"""
        result = subprocess.run(
            [sys.executable, "-c", program], capture_output=True, text=True, timeout=40
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.api = FixtureAPI(Path(self.temporary.name))
        tasks = TaskRegistry()
        accounts = AccountService(self.api, tasks.cancel_account)
        self.first = accounts.add("a", "secret")
        self.second = accounts.add("b", "secret")
        self.application = Application(
            accounts,
            AcademicService(self.api),
            DownloadService(self.api),
            tasks,
            self.api.close,
        )
        self.messages = []
        self.previous_handler = qInstallMessageHandler(
            lambda mode, context, message: self.messages.append(message)
        )
        self.engine, self.model, self.bridge = create_engine(self.application, APP)

    def tearDown(self):
        self.bridge.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.model.deleteLater()
        self.bridge.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.api.close()
        qInstallMessageHandler(self.previous_handler)
        self.temporary.cleanup()

    def pump_until(self, predicate):
        deadline = time.monotonic() + 3
        while not predicate() and time.monotonic() < deadline:
            APP.processEvents()
            threading.Event().wait(0.005)
        APP.processEvents()
        self.assertTrue(predicate(), self.messages)

    def test_actual_qml_loads_with_basic_and_no_warnings(self):
        self.assertEqual(1, len(self.engine.rootObjects()), self.messages)
        self.assertEqual("Basic", QQuickStyle.name())
        APP.processEvents()
        self.assertEqual([], self.messages)

    def test_palette_switch_updates_window_and_persists(self):
        window = self.engine.rootObjects()[0]
        light = window.color().name()
        self.model.setDark(True)
        APP.processEvents()
        self.assertNotEqual(light, window.color().name())
        self.assertEqual("dark", self.application.accounts.color_mode())
        self.model.setDark(False)
        APP.processEvents()
        self.assertEqual(light, window.color().name())

    def test_gui_and_service_return_the_same_score_snapshot(self):
        self.model.queryScores("", False, False)
        self.pump_until(lambda: not self.model.busy)
        self.assertEqual("高等数学", self.model.rows[0]["courseName"])
        self.assertEqual(0, self.model.rows[0]["score"])
        self.assertEqual("已完成", self.model.status)

    def test_progress_notifications_only_modify_model_on_main_thread(self):
        threads = []
        self.model.changed.connect(lambda: threads.append(QThread.currentThread()))
        self.model.queryScores("", False, False)
        self.pump_until(lambda: not self.model.busy)
        self.assertTrue(threads)
        self.assertTrue(all(thread == APP.thread() for thread in threads))

    def test_old_account_result_cannot_populate_new_account(self):
        entered, release = threading.Event(), threading.Event()
        original = self.api.scores

        def blocked(account_id, terms):
            entered.set()
            release.wait(2)
            return original(account_id, terms)

        self.api.scores = blocked
        self.model.queryScores("", False, False)
        self.assertTrue(entered.wait(2))
        self.model.selectAccount(self.second.account_id)
        release.set()
        self.pump_until(self.bridge.idle)
        self.assertEqual([], self.model.rows)
        self.assertEqual(self.second.account_id, self.model.accountId)

    def test_queued_old_events_cannot_replace_new_request(self):
        self.model.queryScores("", False, False)
        old = self.model._task_id
        self.pump_until(self.bridge.idle)
        self.model.queryScores("2025-2026-1", False, False)
        new = self.model._task_id
        self.model._accept(self.application.tasks.snapshot(old))
        self.assertEqual(new, self.model._task_id)
        self.pump_until(lambda: not self.model.busy)
        self.assertEqual("已完成", self.model.status)

    def test_model_destruction_does_not_destroy_running_worker(self):
        entered, release = threading.Event(), threading.Event()
        original = self.api.scores

        def blocked(account_id, terms):
            entered.set()
            release.wait(2)
            return original(account_id, terms)

        self.api.scores = blocked
        self.model.queryScores("", False, False)
        task_id = self.model._task_id
        self.assertTrue(entered.wait(2))
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.model.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        release.set()
        self.pump_until(self.bridge.idle)
        self.assertEqual(
            TaskState.SUCCEEDED, self.application.tasks.snapshot(task_id).state
        )
        # Restore a fresh model/engine solely for uniform teardown.
        self.engine, self.model, unused = create_engine(self.application, APP)
        unused.close()
        unused.deleteLater()

    def test_close_waits_for_cooperative_cleanup(self):
        entered, release = threading.Event(), threading.Event()
        original = self.api.scores

        def blocked(account_id, terms):
            entered.set()
            release.wait(2)
            return original(account_id, terms)

        self.api.scores = blocked
        ready = []
        self.model.quitReady.disconnect()
        self.model.quitReady.connect(lambda: ready.append(True))
        self.model.queryScores("", False, False)
        self.assertTrue(entered.wait(2))
        self.model.requestClose()
        APP.processEvents()
        self.assertEqual([], ready)
        release.set()
        self.pump_until(lambda: bool(ready))
        self.assertTrue(self.bridge.idle())

    def test_resize_and_long_text_do_not_generate_qml_errors(self):
        self.api.score_rows[0]["courseName"] = "很长的课程名称" * 30
        self.model.queryScores("", False, False)
        self.pump_until(lambda: not self.model.busy)
        window = self.engine.rootObjects()[0]
        for width in (620, 1280, 960):
            window.setWidth(width)
            APP.processEvents()
        self.assertEqual([], self.messages)

    def test_high_frequency_progress_is_coalesced_and_terminal_is_kept(self):
        from xjtutoolbox.contracts.tasks import Progress

        notifications = []
        self.bridge.changed.connect(notifications.append)
        task_id = self.application.tasks.register(self.first.account_id)

        def operation(context):
            for number in range(1000):
                context.report(Progress("items", "处理", number, 1000, "items"))
            return "done"

        self.bridge.submit(task_id, operation)
        # Do not pump the UI until the producer has emitted its whole burst.
        deadline = time.monotonic() + 3
        while not self.bridge.idle() and time.monotonic() < deadline:
            threading.Event().wait(0.005)
        APP.processEvents()
        self.assertLess(len(notifications), 10)
        self.assertEqual(TaskState.SUCCEEDED, notifications[-1].state)
        self.assertEqual(999, notifications[-1].progress.completed)
