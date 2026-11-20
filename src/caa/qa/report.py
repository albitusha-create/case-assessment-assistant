"""The gap report a supervisor sees before approving a draft.

Each checklist item ends up as one CheckResult, whether code or the QA agent
checked it. Approval is blocked while any blocking item fails.
"""

from typing import Literal

from pydantic import BaseModel

from caa.rules.completeness import MissingElement


class CheckResult(BaseModel):
    item_id: str
    description: str
    checked_by: Literal["rule", "agent"]
    severity: Literal["blocking", "warning"]
    passed: bool
    findings: list[str]


class QAReport(BaseModel):
    case_id: str
    checklist_version: str
    results: list[CheckResult]
    acknowledged_gaps: list[MissingElement]

    @property
    def blocking_failures(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "blocking"]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity == "warning"]

    @property
    def can_approve(self) -> bool:
        return not self.blocking_failures
