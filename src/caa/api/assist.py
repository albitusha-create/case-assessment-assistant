"""The assistant inside the agency portal: check one form section on request.

The portal's form page loads a small script from us (static/portal-assistant.js),
the way an agency system hosts a sidebar app from a vendor. The script calls
these endpoints with the worker's current text. We read the form's schema from
the portal's API, as for pre-fill, and log every check to our audit trail.
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from caa.api.auth import CASEWORKER, User, current_user, require_role
from caa.api.routes import CaseDep, PortalClientDep, StoreDep
from caa.assist.section_check import MAX_TEXT, SectionCheck, SectionChecker, assist_allowed
from caa.integrations.portal_client import PortalError
from caa.portal.form import Domain, FormSchema
from caa.storage.store import AuditEvent

router = APIRouter(prefix="/api/assist")


def get_checker(request: Request) -> SectionChecker:
    checker: SectionChecker = request.app.state.section_checker
    return checker


def portal_schema(portal: PortalClientDep) -> FormSchema:
    try:
        return portal.get_schema()
    except PortalError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The agency portal could not be read"
        ) from exc


SchemaDep = Annotated[FormSchema, Depends(portal_schema)]


@router.get("/cases/{case_id}/sections")
def sections(
    case: CaseDep, schema: SchemaDep, _: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    """Form sections the assistant can check: worker sections it may also pre-fill."""
    return {
        "case_id": case.case_id,
        "sections": [{"id": d.id, "title": d.title} for d in schema.domains if assist_allowed(d)],
    }


@router.post("/cases/{case_id}/sections/{domain_id}/check")
async def check(
    case: CaseDep,
    domain_id: str,
    schema: SchemaDep,
    store: StoreDep,
    checker: Annotated[SectionChecker, Depends(get_checker)],
    user: Annotated[User, Depends(require_role(CASEWORKER))],
    text: Annotated[str, Body(embed=True, max_length=MAX_TEXT)],
) -> SectionCheck:
    domain: Domain | None = schema.domain(domain_id)
    if domain is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown form section")
    if not assist_allowed(domain):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{domain.title} is completed by the clinician or in the person's own words. "
            "The assistant does not review it.",
        )
    try:
        # The model call blocks for a few seconds; keep the event loop free.
        result = await run_in_threadpool(checker, case.case_id, domain, text)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The assistant could not check this section. Try again."
        ) from exc
    store.add_event(
        AuditEvent(
            case_id=case.case_id,
            actor=user.name,
            action="portal_section_checked",
            details={
                "section": domain.title,
                "open_items": result.open_items,
                "suggestions": len(result.suggestions),
                "characters": len(text),
            },
        )
    )
    return result


@router.post("/cases/{case_id}/sections/{domain_id}/inserted", status_code=204)
def suggestion_inserted(
    case: CaseDep,
    domain_id: str,
    schema: SchemaDep,
    store: StoreDep,
    user: Annotated[User, Depends(require_role(CASEWORKER))],
    doc_id: Annotated[str, Body(max_length=100)],
    page: Annotated[int, Body(ge=1)],
) -> None:
    """The worker inserted a suggested fact into the field. Logged, not stored as text."""
    domain = schema.domain(domain_id)
    if domain is None or not assist_allowed(domain):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown form section")
    store.add_event(
        AuditEvent(
            case_id=case.case_id,
            actor=user.name,
            action="portal_suggestion_inserted",
            details={"section": domain.title, "source": f"{doc_id}, page {page}"},
        )
    )
