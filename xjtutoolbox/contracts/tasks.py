from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Progress:
    stage: str
    message: str
    completed: int | None = None
    total: int | None = None
    unit: str = ""
    overall: float | None = None

    def __post_init__(self) -> None:
        if self.completed is not None and self.completed < 0:
            raise ValueError("completed must be nonnegative")
        if self.total is not None and self.total <= 0:
            raise ValueError("total must be positive or unknown")
        if self.overall is not None and (
            not math.isfinite(self.overall) or not 0 <= self.overall <= 100
        ):
            raise ValueError("overall must be between 0 and 100")


class RunContext(Protocol):
    def check_cancelled(self) -> None: ...
    def report(self, progress: Progress) -> None: ...


class NullContext:
    def check_cancelled(self) -> None:
        pass

    def report(self, progress: Progress) -> None:
        pass
