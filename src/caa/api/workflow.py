"""Case state changes and their audit events. No HTTP here, so it is easy to test.

The rules for a human decision live in code:
- Only a draft with no open blocking QA item can be approved.
- A supervisor may dismiss a failed item that the QA agent judged, with a
  reason. Items checked by rules can never be dismissed: fix the draft instead.
- Returning a draft for changes needs a comment.
"""

from collections.abc import Callable

from caa.agents.definitions import DRAFTING_AGENT, QA_AGENT
from caa.agents.pipeline import CaseRun
from caa.api.auth import User
from caa.qa.report import QAReport
from caa.storage.store import AuditEvent, CaseRecord, Dismissal, Store, now
from caa.synthetic import SyntheticCase

CaseRunner = Callable[[SyntheticCase], CaseRun]


class WorkflowError(Exception):
    """A request that the case's current state does not allow."""


def run_and_record(store: Store, runner: CaseRunner, case: SyntheticCase, user: User) -> CaseRecord:
    store.add_event(AuditEvent(case_id=case.case_id, actor=user.name, action="run_started"))
    run = runner(case)
    if run.report is None:
        raise WorkflowError("The run did not produce a QA report")

    record = CaseRecord(
        case_id=case.case_id, status="in_review", draft=run.drafted.draft, report=run.report
    )
    store.save_case(record)
    store.add_event(
        AuditEvent(
            case_id=case.case_id,
            actor=DRAFTING_AGENT,
            action="drafted",
            details={
                "facts_extracted": len(run.facts.facts),
                "facts_rejected": len(run.facts.rejected),
                "dropped_citations": run.drafted.dropped_citations,
            },
        )
    )
    report = run.report
    store.add_event(
        AuditEvent(
            case_id=case.case_id,
            actor=QA_AGENT,
            action="qa_completed",
            details={
                "checklist_version": report.checklist_version,
                "blocking": [r.item_id for r in report.blocking_failures],
                "warnings": [r.item_id for r in report.warnings],
                "can_approve": report.can_approve,
            },
        )
    )
    return record


def _in_review(store: Store, case_id: str) -> tuple[CaseRecord, QAReport]:
    record = store.get_case(case_id)
    if record is None or record.status != "in_review" or record.report is None:
        raise WorkflowError("There is no draft waiting for review")
    return record, record.report


def dismiss_finding(
    store: Store, case_id: str, user: User, item_id: str, reason: str
) -> CaseRecord:
    if not reason.strip():
        raise WorkflowError("A reason is required to dismiss a finding")
    record, report = _in_review(store, case_id)
    result = next((r for r in report.results if r.item_id == item_id), None)
    if result is None or result.passed:
        raise WorkflowError(f"No failed QA item named {item_id}")
    if result.checked_by != "agent":
        raise WorkflowError(f"{item_id} is checked by a rule and cannot be dismissed")
    record.dismissals[item_id] = Dismissal(by=user.name, reason=reason)
    record.updated_at = now()
    store.save_case(record)
    store.add_event(
        AuditEvent(
            case_id=case_id,
            actor=user.name,
            action="finding_dismissed",
            details={"item_id": item_id, "reason": reason, "findings": result.findings},
        )
    )
    return record


def approve(store: Store, case_id: str, user: User) -> CaseRecord:
    record, _ = _in_review(store, case_id)
    if not record.can_approve:
        blocking = ", ".join(r.item_id for r in record.open_blockers)
        raise WorkflowError(f"Blocking QA items must be resolved first: {blocking}")
    record.status, record.updated_at = "approved", now()
    store.save_case(record)
    store.add_event(
        AuditEvent(
            case_id=case_id,
            actor=user.name,
            action="approved",
            details={"dismissed_items": sorted(record.dismissals)},
        )
    )
    return record


def return_for_changes(store: Store, case_id: str, user: User, comment: str) -> CaseRecord:
    if not comment.strip():
        raise WorkflowError("A comment is required when returning a draft")
    record, _ = _in_review(store, case_id)
    record.status, record.updated_at = "returned", now()
    store.save_case(record)
    store.add_event(
        AuditEvent(
            case_id=case_id, actor=user.name, action="returned", details={"comment": comment}
        )
    )
    return record
