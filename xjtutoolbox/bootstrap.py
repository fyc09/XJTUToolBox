"""Composition root only: construct dependencies and inject entrypoints."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from platformdirs import user_data_path

from xjtutoolbox.api import CampusAPI
from xjtutoolbox.infrastructure.storage import AccountStore
from xjtutoolbox.runtime import TaskRegistry
from xjtutoolbox.services import AccountService, AcademicService, DownloadService


@dataclass
class Application:
    accounts: AccountService
    academic: AcademicService
    downloads: DownloadService
    tasks: TaskRegistry
    close: Callable[[], None]


def build_application(directory: Path | None = None) -> Application:
    api = CampusAPI(
        AccountStore(
            directory
            if directory is not None
            else user_data_path("XJTUToolBox", "XJTUToolBox")
        )
    )
    tasks = TaskRegistry()
    return Application(
        AccountService(api, tasks.cancel_account),
        AcademicService(api),
        DownloadService(api),
        tasks,
        api.close,
    )
