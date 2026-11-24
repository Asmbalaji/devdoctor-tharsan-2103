from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List

EXIT_OK = 0
EXIT_WARN = 1
EXIT_FAIL = 2
EXIT_CONFIG = 3  # unreadable/malformed config or bad CLI usage


class Status(IntEnum):
    OK = 0
    WARN = 1
    FAIL = 2

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass
class CheckResult:
    id: str
    title: str
    status: Status
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.label,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class Report:
    checks: List[CheckResult]
    platform: Dict[str, str]
    tool_version: str
    fail_on: str = "warn"  # "warn": warnings give exit 1; "fail": only failures are non-zero

    @property
    def overall(self) -> Status:
        return max((c.status for c in self.checks), default=Status.OK)

    @property
    def exit_code(self) -> int:
        if self.overall is Status.FAIL:
            return EXIT_FAIL
        if self.overall is Status.WARN and self.fail_on == "warn":
            return EXIT_WARN
        return EXIT_OK

    def summary(self) -> Dict[str, int]:
        return {s.label: sum(1 for c in self.checks if c.status is s) for s in Status}
