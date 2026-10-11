from __future__ import annotations

import argparse
import getpass
import json
import os
import signal
import sys
from dataclasses import asdict, is_dataclass, replace
from typing import Sequence

from xjtutoolbox.contracts.data import (
    AppError,
    ChallengeAnswer,
    DownloadRequest,
    ScoreRequest,
)
from xjtutoolbox.runtime import TaskState


EXIT_SUCCESS, EXIT_FAILURE, EXIT_INPUT, EXIT_CANCELLED = 0, 1, 3, 130


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="xjtutoolbox")
    result.add_argument("--data-dir", help="账户元数据和设置目录")
    commands = result.add_subparsers(dest="command", required=True)
    accounts = commands.add_parser("accounts")
    actions = accounts.add_subparsers(dest="action", required=True)
    for name in ("list", "add", "remove", "unlock"):
        action = actions.add_parser(name)
        action.add_argument("--json", action="store_true")
        if name == "add":
            action.add_argument("username")
            action.add_argument("--nickname", default="")
            action.add_argument(
                "--kind",
                choices=("undergraduate", "postgraduate"),
                default="undergraduate",
            )
            action.add_argument(
                "--remember", action="store_true", help="使用系统 keyring 保存密码"
            )
        elif name != "list":
            action.add_argument("account_id")
    for name in ("scores", "download"):
        command = commands.add_parser(name)
        command.add_argument("--account", required=True)
        command.add_argument("--json", action="store_true")
        command.add_argument(
            "--interactive", action="store_true", help="在终端继续 MFA/图片验证码验证"
        )
        if name == "scores":
            group = command.add_mutually_exclusive_group()
            group.add_argument("--term", action="append")
            group.add_argument("--current-term", action="store_true")
            command.add_argument("--report", action="store_true")
        else:
            command.add_argument("url")
            command.add_argument("destination")
    return result


def _password() -> str:
    password = os.environ.get("XJTUTOOLBOX_PASSWORD")
    if password is not None:
        return password
    if not sys.stdin.isatty():
        raise AppError("请设置 XJTUTOOLBOX_PASSWORD，或在交互终端输入密码")
    return getpass.getpass("密码：")


def _write(value, machine: bool) -> None:
    if is_dataclass(value):
        value = asdict(value)
    if machine:
        print(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, dict) and "rows" in value:
        for row in value["rows"]:
            print(
                f"{row['courseName']}\t{row.get('score', '')}\t{row.get('coursePoint', '')}\t{row.get('gpa', '')}"
            )
    elif isinstance(value, list):
        for row in value:
            print(f"{row['account_id']}\t{row['nickname']}\t{row['kind']}")
    else:
        print(json.dumps(value, ensure_ascii=False))


def main(argv: Sequence[str] | None = None, *, application=None) -> int:
    args = parser().parse_args(argv)
    owned = application is None
    if owned:
        from pathlib import Path
        from xjtutoolbox.bootstrap import build_application

        application = build_application(Path(args.data_dir) if args.data_dir else None)
    try:
        if args.command == "accounts":
            if args.action == "list":
                value = [asdict(a) for a in application.accounts.list_accounts()]
            elif args.action == "add":
                value = application.accounts.add(
                    args.username, _password(), args.nickname, args.kind, args.remember
                )
            elif args.action == "unlock":
                application.accounts.unlock(args.account_id, _password())
                value = {"account_id": args.account_id, "unlocked": True}
            else:
                application.accounts.remove(args.account_id)
                value = {"account_id": args.account_id, "removed": True}
            _write(value, args.json)
            return EXIT_SUCCESS
        if "XJTUTOOLBOX_PASSWORD" in os.environ:
            application.accounts.unlock(
                args.account, os.environ["XJTUTOOLBOX_PASSWORD"]
            )
        if args.command == "scores":
            request = ScoreRequest(
                args.account,
                tuple(args.term) if args.term else None,
                args.current_term,
                args.report,
            )
            operation = application.academic.query_scores
        else:
            request = DownloadRequest(args.account, args.url, args.destination)
            operation = application.downloads.download
        while True:
            task_id = application.tasks.register(args.account)

            def on_interrupt(signum, frame):
                application.tasks.cancel(task_id)

            previous = signal.signal(signal.SIGINT, on_interrupt)

            def show_progress(task):
                if (
                    task.task_id == task_id
                    and task.state == TaskState.RUNNING
                    and task.progress
                ):
                    progress = task.progress
                    amount = (
                        ""
                        if progress.completed is None
                        else f" {progress.completed}/{progress.total or '?'} {progress.unit}"
                    )
                    print(progress.message + amount, file=sys.stderr)

            unsubscribe = application.tasks.subscribe(show_progress)
            try:
                task = application.tasks.run(
                    task_id, lambda context: operation(request, context)
                )
            finally:
                unsubscribe()
                signal.signal(signal.SIGINT, previous)
            if task.state == TaskState.SUCCEEDED:
                _write(task.result, args.json)
                return EXIT_SUCCESS
            if task.state == TaskState.CANCELLED:
                print("操作已取消", file=sys.stderr)
                return EXIT_CANCELLED
            challenge = task.error.challenge
            if challenge is not None and args.interactive and sys.stdin.isatty():
                if challenge.image_base64:
                    print(
                        "验证码图片（浏览器 data URL）：data:image/png;base64,"
                        + challenge.image_base64,
                        file=sys.stderr,
                    )
                print(challenge.prompt + "：", file=sys.stderr)
                answer = input()
                request = replace(
                    request, answer=ChallengeAnswer(challenge.challenge_id, answer)
                )
                continue
            print(task.error.message, file=sys.stderr)
            if args.json:
                _write({"error": asdict(task.error)}, True)
            return EXIT_INPUT if challenge is not None else EXIT_FAILURE
    except KeyboardInterrupt:
        return EXIT_CANCELLED
    except AppError as exc:
        print(str(exc), file=sys.stderr)
        if args.json:
            _write({"error": {"code": exc.code, "message": str(exc)}}, True)
        return EXIT_FAILURE
    finally:
        if owned:
            application.tasks.begin_shutdown()
            application.close()
