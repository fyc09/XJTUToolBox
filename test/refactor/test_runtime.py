import threading
import unittest

TEST_DOMAIN = "core"

from xjtutoolbox.contracts.data import AppError, Cancelled
from xjtutoolbox.contracts.tasks import Progress
from xjtutoolbox.runtime import TaskRegistry, TaskState


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tasks = TaskRegistry()
        self.events = []
        self.tasks.subscribe(self.events.append)
        self.task_id = self.tasks.register("account-a")

    def test_normal_none_return_is_success(self):
        task = self.tasks.run(self.task_id, lambda context: None)
        self.assertEqual(TaskState.SUCCEEDED, task.state)
        self.assertIsNone(task.result)

    def test_library_system_exit_cannot_leave_task_running(self):
        def operation(context):
            raise SystemExit(0)

        task = self.tasks.run(self.task_id, operation)
        self.assertEqual(TaskState.FAILED, task.state)
        self.assertEqual(1, sum(e.state == TaskState.FAILED for e in self.events))

    def test_keyboard_interrupt_is_finalized_as_cancellation(self):
        def operation(context):
            raise KeyboardInterrupt()

        task = self.tasks.run(self.task_id, operation)
        self.assertEqual(TaskState.CANCELLED, task.state)

    def test_full_progress_does_not_turn_exception_into_success(self):
        def operation(context):
            context.report(Progress("save", "保存", overall=100))
            raise AppError("保存失败")

        task = self.tasks.run(self.task_id, operation)
        self.assertEqual(TaskState.FAILED, task.state)
        self.assertEqual("保存失败", task.error.message)

    def test_pending_cancellation_never_calls_operation(self):
        self.tasks.cancel(self.task_id)
        task = self.tasks.run(
            self.task_id, lambda context: self.fail("cancelled work ran")
        )
        self.assertEqual(TaskState.CANCELLED, task.state)

    def test_running_cancellation_is_not_terminal_until_cleanup(self):
        entered, release, cleaned = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def operation(context):
            try:
                entered.set()
                self.assertTrue(release.wait(2))
                context.check_cancelled()
            finally:
                cleaned.set()

        worker = threading.Thread(target=self.tasks.run, args=(self.task_id, operation))
        worker.start()
        self.assertTrue(entered.wait(2))
        self.tasks.cancel(self.task_id)
        self.assertEqual(TaskState.RUNNING, self.tasks.snapshot(self.task_id).state)
        self.assertFalse(cleaned.is_set())
        release.set()
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(cleaned.is_set())
        self.assertEqual(TaskState.CANCELLED, self.tasks.snapshot(self.task_id).state)

    def test_late_cancellation_preserves_committed_success(self):
        def operation(context):
            self.tasks.cancel(self.task_id)
            return {"committed": True}

        task = self.tasks.run(self.task_id, operation)
        self.assertEqual(TaskState.SUCCEEDED, task.state)
        self.tasks.cancel(self.task_id)
        self.assertEqual(task, self.tasks.snapshot(self.task_id))

    def test_cancelled_partial_side_effects_are_retained(self):
        def operation(context):
            raise Cancelled(
                partial_result={"completed": ["one"], "unexecuted": ["two"]}
            )

        task = self.tasks.run(self.task_id, operation)
        self.assertEqual(["one"], task.result["completed"])

    def test_late_progress_cannot_modify_terminal_task(self):
        contexts = []
        task = self.tasks.run(self.task_id, lambda context: contexts.append(context))
        contexts[0].report(Progress("late", "迟到"))
        self.assertEqual(task, self.tasks.snapshot(self.task_id))

    def test_duplicate_run_has_one_terminal_event(self):
        self.tasks.run(self.task_id, lambda context: 1)
        self.tasks.run(self.task_id, lambda context: self.fail("duplicate execution"))
        self.assertEqual(1, sum(e.state == TaskState.SUCCEEDED for e in self.events))

    def test_duplicate_concurrent_run_does_not_execute_twice(self):
        entered, release = threading.Event(), threading.Event()

        def operation(context):
            entered.set()
            release.wait(2)
            return "done"

        worker = threading.Thread(target=self.tasks.run, args=(self.task_id, operation))
        worker.start()
        self.assertTrue(entered.wait(2))
        self.tasks.run(self.task_id, lambda context: self.fail("duplicate execution"))
        release.set()
        worker.join(2)
        self.assertEqual("done", self.tasks.snapshot(self.task_id).result)

    def test_account_cancel_does_not_cancel_another_account(self):
        other = self.tasks.register("account-b")
        self.tasks.cancel_account("account-a")
        self.assertEqual(TaskState.PENDING, self.tasks.snapshot(other).state)

    def test_shutdown_rejects_new_tasks(self):
        self.tasks.begin_shutdown()
        with self.assertRaises(RuntimeError):
            self.tasks.register("a")

    def test_unsubscribe_prevents_further_delivery(self):
        events = []
        unsubscribe = self.tasks.subscribe(events.append)
        unsubscribe()
        self.tasks.run(self.task_id, lambda context: None)
        self.assertEqual([], events)

    def test_listener_failure_does_not_strand_task(self):
        self.tasks.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError()))
        self.assertEqual(
            TaskState.SUCCEEDED,
            self.tasks.run(self.task_id, lambda context: None).state,
        )

    def test_snapshots_cannot_mutate_saved_results(self):
        task = self.tasks.run(self.task_id, lambda context: {"rows": [1]})
        task.result["rows"].append(2)
        self.assertEqual([1], self.tasks.snapshot(self.task_id).result["rows"])

    def test_unexpected_exception_details_do_not_leak(self):
        def operation(context):
            raise RuntimeError("password=secret")

        task = self.tasks.run(self.task_id, operation)
        self.assertNotIn("secret", task.error.message)

    def test_unknown_total_is_distinct_from_zero(self):
        self.assertIsNone(Progress("download", "下载", completed=0).total)
        with self.assertRaises(ValueError):
            Progress("download", "下载", total=0)

    def test_nonfinite_progress_is_rejected(self):
        for value in (float("inf"), float("nan"), -1, 101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Progress("x", "x", overall=value)
