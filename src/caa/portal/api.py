"""The mock portal's REST API, version 1, as a vendor would publish it.

Every call needs `Authorization: Bearer <PORTAL_API_KEY>`. There is a save-draft
operation and no submit operation: submitting is a person's click in the portal.
"""

import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from caa.config import Settings, get_settings
from caa.portal.form import FormSchema
from caa.portal.store import (
    DOCUMENTS_DIR,
    AssessmentForm,
    DraftIn,
    PortalCase,
    PortalConflict,
    PortalStore,
    PortalValidationError,
)

router = APIRouter(prefix="/portal/api/v1", tags=["agency portal (mock)"])


def get_portal(request: Request) -> PortalStore:
    portal: PortalStore = request.app.state.portal
    return portal


def api_client(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str, Header()] = "",
) -> str:
    """Checks the bearer key and returns the client's name for the form's history."""
    if not settings.portal_api_key:
        if settings.environment == "local":
            return "local-client"
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Portal API key not configured")
    scheme, _, key = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(key, settings.portal_api_key):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or wrong API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "api-client"


PortalDep = Annotated[PortalStore, Depends(get_portal)]
Client = Annotated[str, Depends(api_client)]


def found(portal: PortalStore, case_id: str) -> PortalCase:
    try:
        return portal.get_case(case_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown case") from exc


class CaseSummary(BaseModel):
    case_id: str
    case_number: str
    client_name: str
    program: str
    assigned_worker: str
    assessment_due: str
    form_status: str


@router.get("/cases")
def list_cases(portal: PortalDep, _: Client) -> list[CaseSummary]:
    return [
        CaseSummary(
            case_id=c.case_id,
            case_number=c.case_number,
            client_name=c.client_name,
            program=c.program,
            assigned_worker=c.assigned_worker,
            assessment_due=c.assessment_due.isoformat(),
            form_status=portal.get_form(c.case_id).status,
        )
        for c in portal.list_cases()
    ]


@router.get("/cases/{case_id}")
def get_case(case_id: str, portal: PortalDep, _: Client) -> PortalCase:
    return found(portal, case_id)


def document_path(case: PortalCase, doc_id: str) -> Path:
    """Only documents listed on the case are served, so doc_id never builds an arbitrary path."""
    if case.document(doc_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown document")
    return DOCUMENTS_DIR / case.case_id / f"{doc_id}.pdf"


@router.get("/cases/{case_id}/documents/{doc_id}")
def get_document(case_id: str, doc_id: str, portal: PortalDep, _: Client) -> FileResponse:
    path = document_path(found(portal, case_id), doc_id)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document file not available")
    return FileResponse(path, media_type="application/pdf")


@router.get("/forms/core-assessment/schema")
def get_schema(portal: PortalDep, _: Client) -> FormSchema:
    return portal.schema


@router.get("/cases/{case_id}/assessment")
def get_assessment(case_id: str, portal: PortalDep, _: Client) -> AssessmentForm:
    found(portal, case_id)
    return portal.get_form(case_id)


@router.put("/cases/{case_id}/assessment/draft")
def save_draft(
    case_id: str,
    draft: DraftIn,
    portal: PortalDep,
    client: Client,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=200)],
) -> AssessmentForm:
    """Save a pre-filled draft for the worker to review. Never submits."""
    found(portal, case_id)
    try:
        form, _ = portal.save_prefill(case_id, draft, client, idempotency_key)
    except PortalConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except PortalValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return form
