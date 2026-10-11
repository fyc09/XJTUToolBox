import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

TEST_DOMAIN = "core"

from test.refactor.test_services import FixtureAPI
from xjtutoolbox.bootstrap import Application
from xjtutoolbox.cli.main import main
from xjtutoolbox.contracts.data import Challenge, InputRequired, ScoreRequest
from xjtutoolbox.contracts.tasks import NullContext
from xjtutoolbox.runtime import TaskRegistry
from xjtutoolbox.services import AccountService, AcademicService, DownloadService


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        api = FixtureAPI(Path(self.temporary.name))
        self.addCleanup(api.close)
        tasks = TaskRegistry()
        self.app = Application(
            AccountService(api, tasks.cancel_account),
            AcademicService(api),
            DownloadService(api),
            tasks,
            api.close,
        )
        self.account = self.app.accounts.add("a", "secret")

    def invoke(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            code = main(arguments, application=self.app)
        return code, output.getvalue(), errors.getvalue()

    def test_json_result_matches_direct_service_result(self):
        code, output, errors = self.invoke(
            ["scores", "--account", self.account.account_id, "--json"]
        )
        expected = asdict(
            self.app.academic.query_scores(
                ScoreRequest(self.account.account_id), NullContext()
            )
        )
        self.assertEqual(0, code)
        self.assertEqual(json.loads(json.dumps(expected)), json.loads(output))
        self.assertIn("正在查询成绩", errors)
        self.assertNotIn("正在查询成绩", output)

    def test_business_failure_has_nonzero_exit_code(self):
        code, output, errors = self.invoke(
            ["scores", "--account", self.account.account_id, "--term", "bad", "--json"]
        )
        self.assertEqual(1, code)
        self.assertEqual("business_error", json.loads(output)["error"]["code"])

    def test_missing_account_is_failure_not_empty_success(self):
        code, output, errors = self.invoke(["scores", "--account", "missing", "--json"])
        self.assertEqual(1, code)
        self.assertEqual("account_invalid", json.loads(output)["error"]["code"])

    def test_input_required_has_dedicated_exit_and_account_bound_json(self):
        challenge = Challenge(
            "challenge", self.account.account_id, "jwxt", "mfa", "验证码"
        )

        def operation(*args):
            raise InputRequired(challenge)

        self.app.academic.query_scores = operation
        code, output, errors = self.invoke(
            ["scores", "--account", self.account.account_id, "--json"]
        )
        self.assertEqual(3, code)
        self.assertEqual(
            self.account.account_id,
            json.loads(output)["error"]["challenge"]["account_id"],
        )

    def test_cancelled_operation_returns_130(self):
        def operation(request, context):
            self.app.tasks.cancel_account(request.account_id)
            context.check_cancelled()

        self.app.academic.query_scores = operation
        code, output, errors = self.invoke(
            ["scores", "--account", self.account.account_id, "--json"]
        )
        self.assertEqual(130, code)
        self.assertEqual("", output)

    def test_interactive_verification_keeps_json_output_clean(self):
        challenge = Challenge(
            "challenge", self.account.account_id, "jwxt", "mfa", "验证码"
        )
        original = self.app.academic.query_scores

        def operation(request, context):
            if request.answer is None:
                raise InputRequired(challenge)
            self.assertEqual("123456", request.answer.value)
            return original(request, context)

        self.app.academic.query_scores = operation
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", return_value="123456") as read,
        ):
            code, output, errors = self.invoke(
                [
                    "scores",
                    "--account",
                    self.account.account_id,
                    "--interactive",
                    "--json",
                ]
            )
        self.assertEqual(0, code)
        self.assertEqual("高等数学", json.loads(output)["rows"][0]["courseName"])
        read.assert_called_once_with()
        self.assertIn("验证码", errors)

    def test_accounts_list_has_no_password_field(self):
        code, output, errors = self.invoke(["accounts", "list", "--json"])
        self.assertEqual(0, code)
        self.assertEqual(self.account.account_id, json.loads(output)[0]["account_id"])
        self.assertNotIn("secret", output)

    def test_account_add_reads_password_from_environment_not_arguments(self):
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"XJTUTOOLBOX_PASSWORD": "hidden"}),
            redirect_stdout(output),
        ):
            code = main(["accounts", "add", "b", "--json"], application=self.app)
        self.assertEqual(0, code)
        self.assertNotIn("hidden", output.getvalue())

    def test_download_uses_same_service_and_returns_file_result(self):
        destination = str(Path(self.temporary.name) / "attachment")
        code, output, errors = self.invoke(
            [
                "download",
                "--account",
                self.account.account_id,
                "https://lms.xjtu.edu.cn/file",
                destination,
                "--json",
            ]
        )
        self.assertEqual(0, code)
        self.assertEqual(6, json.loads(output)["bytes_written"])
        self.assertEqual(b"onetwo", Path(destination).read_bytes())
