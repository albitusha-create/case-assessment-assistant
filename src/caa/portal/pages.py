"""The mock portal's own pages: what a worker sees in the agency system.

Signed-in users reach these pages through the same Entra sign-in as our app,
standing in for the agency's single sign-on. Only Caseworkers save or submit.
"""

from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from caa.api.auth import CASEWORKER, User, current_user, require_role
from caa.portal.api import PortalDep, document_path, found
from caa.portal.store import FormHeader, PortalConflict, PortalValidationError

TEMPLATES = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
router = APIRouter(prefix="/portal", include_in_schema=False)

SignedIn = Annotated[User, Depends(current_user)]
Worker = Annotated[User, Depends(require_role(CASEWORKER))]


def to_form(case_id: str, message: str = "") -> RedirectResponse:
    url = f"/portal/cases/{case_id}/assessment"
    if message:
        url += f"?msg={quote(message)}"
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse)
def case_list(request: Request, portal: PortalDep, user: SignedIn) -> HTMLResponse:
    rows = [(c, portal.get_form(c.case_id)) for c in portal.list_cases()]
    return TEMPLATES.TemplateResponse(
        request, "portal_cases.html", {"rows": rows, "user": user, "today": date.today()}
    )


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def case_record(request: Request, case_id: str, portal: PortalDep, user: SignedIn) -> HTMLResponse:
    case = found(portal, case_id)
    context = {"case": case, "form": portal.get_form(case_id), "user": user}
    return TEMPLATES.TemplateResponse(request, "portal_case.html", context)


@router.get("/cases/{case_id}/documents/{doc_id}")
def document(case_id: str, doc_id: str, portal: PortalDep, _: SignedIn) -> FileResponse:
    path = document_path(found(portal, case_id), doc_id)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file not available")
    return FileResponse(path, media_type="application/pdf")


@router.get("/cases/{case_id}/assessment", response_class=HTMLResponse)
def assessment(
    request: Request, case_id: str, portal: PortalDep, user: SignedIn, msg: str = ""
) -> HTMLResponse:
    case = found(portal, case_id)
    context = {
        "case": case,
        "form": portal.get_form(case_id),
        "schema": portal.schema,
        "user": user,
        "msg": msg,
    }
    return TEMPLATES.TemplateResponse(request, "portal_form.html", context)


def parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


@router.post("/cases/{case_id}/assessment")
async def save_assessment(
    request: Request, case_id: str, portal: PortalDep, user: Worker
) -> RedirectResponse:
    found(portal, case_id)
    data = await request.form()

    def text(name: str) -> str:
        value = data.get(name, "")
        return value if isinstance(value, str) else ""

    try:
        header = FormHeader.model_validate(
            dict(
                assessment_type=text("assessment_type") or None,
                abbreviated=text("abbreviated") == "on",
                abbreviated_reason=text("abbreviated_reason"),
                date_started=parse_date(text("date_started")),
                date_completed=parse_date(text("date_completed")),
                meeting_dates=text("meeting_dates"),
                outside_provider=text("outside_provider") == "on",
                information_sources=[
                    v for v in data.getlist("information_sources") if isinstance(v, str)
                ],
                sources_detail=text("sources_detail"),
                preferred_name=text("preferred_name"),
                pronouns=text("pronouns"),
            )
        )
        domains = {d.id: text(f"domain_{d.id}") for d in portal.schema.domains}
        portal.worker_save(case_id, user.name, header, domains)
        if text("action") == "submit":
            portal.submit(case_id, user.name, attested=text("attest") == "on")
            return to_form(case_id, "Assessment submitted.")
    except (PortalConflict, PortalValidationError, ValueError) as exc:
        return to_form(case_id, str(exc))
    return to_form(case_id, "Draft saved.")
