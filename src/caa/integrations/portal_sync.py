"""The steps where our workflow meets the agency portal, each written to the audit log.

1. Before drafting: pull the case record from the portal (portal_case_pulled).
2. After the supervisor approves: map the draft onto the portal form and save it
   there as a draft (portal_draft_pushed). The worker reviews and submits it in
   the portal. If the portal refuses, approval still stands and the refusal is
   logged (portal_push_rejected or portal_push_failed), so it can be retried.
3. When the worker submits: the portal's webhook arrives (submitted_in_portal),
   with how many pre-filled domains the worker changed.

A portal outage never blocks drafting or approval in our app.
"""

from caa.api.auth import User
from caa.integrations.form_mapping import draft_to_form
from caa.integrations.portal_client import PortalClient, PortalConflictError, PortalError
from caa.portal.store import AssessmentForm, PortalCase, SubmittedEvent
from caa.storage.store import AuditEvent, Store
from caa.synthetic import SyntheticCase

PORTAL_ACTOR = "agency-portal"


class PushError(Exception):
    """Nothing to push: the case is not approved."""


def pull_case(store: Store, client: PortalClient, case_id: str, user: User) -> PortalCase | None:
    try:
        case = client.get_case(case_id)
    except PortalError as exc:
        store.add_event(
            AuditEvent(
                case_id=case_id,
                actor=user.name,
                action="portal_pull_failed",
                details={"error": str(exc)},
            )
        )
        return None
    store.add_event(
        AuditEvent(
            case_id=case_id,
            actor=user.name,
            action="portal_case_pulled",
            details={
                "case_number": case.case_number,
                "documents": [d.doc_id for d in case.documents],
                "assessment_due": case.assessment_due.isoformat(),
            },
        )
    )
    return case


def push_approved_draft(
    store: Store, client: PortalClient, case: SyntheticCase, user: User
) -> AssessmentForm | None:
    record = store.get_case(case.case_id)
    if record is None or record.status != "approved" or record.draft is None:
        raise PushError("Only an approved draft can be sent to the portal")
    # One key per approval: a retry of the same approval is a no-op in the portal.
    key = f"{case.case_id}:approved:{record.updated_at:%Y%m%dT%H%M%S%f}"

    def log(action: str, details: dict[str, object]) -> None:
        store.add_event(
            AuditEvent(case_id=case.case_id, actor=user.name, action=action, details=details)
        )

    try:
        portal_case = client.get_case(case.case_id)
        payload = draft_to_form(record.draft, portal_case, client.get_schema(), case.start_date)
        form = client.save_draft(case.case_id, payload, key)
    except PortalConflictError as exc:
        log("portal_push_rejected", {"reason": str(exc), "idempotency_key": key})
        return None
    except PortalError as exc:
        log("portal_push_failed", {"error": str(exc), "idempotency_key": key})
        return None
    log(
        "portal_draft_pushed",
        {
            "form": f"{form.form_id} v{form.form_version}",
            "prefilled_domains": sorted(payload.domains),
            "clinician_references": sorted(payload.references),
            "ask_in_interview": payload.ask_in_interview,
            "idempotency_key": key,
        },
    )
    return form


def record_submitted(store: Store, event: SubmittedEvent) -> None:
    store.add_event(
        AuditEvent(
            case_id=event.case_id,
            actor=PORTAL_ACTOR,
            action="submitted_in_portal",
            details={
                "submitted_by": event.submitted_by,
                "prefilled_domains": event.prefilled_domains,
                "changed_by_worker": event.changed_by_worker,
            },
        )
    )
