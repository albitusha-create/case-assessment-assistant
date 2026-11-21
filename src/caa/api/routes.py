"""HTTP routes: HTML pages for people, plus one JSON endpoint for integrations.

Pages use plain HTML forms that post and redirect back to the case page, so
there is no front-end framework to explain.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from caa.agents.definitions import DRAFTING_AGENT, QA_AGENT
from caa.api.auth import CASEWORKER, SUPERVISOR, User, current_user, require_role
from caa.api.workflow import (
    CaseRunner,
    WorkflowError,
    approve,
    dismiss_finding,
    return_for_changes,
    run_and_record,
)
from caa.integrations.portal_client import PortalClient
from caa.integrations.portal_sync import PushError, pull_case, push_approved_draft
from caa.storage.store import AuditEvent, Store
from caa.synthetic import (
    SyntheticCase,
    list_case_ids,
    list_source_docs,
    load_case,
    load_source_page,
)

TEMPLATES = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "web" / "templates")
router = APIRouter()

Tab = Literal["draft", "qa", "audit"]

# Audit actions as people read them. Unknown actions fall back to the raw name.
ACTION_LABELS = {
    "run_started": "Assessment run started",
    "drafted": "Draft generated",
    "qa_completed": "QA checks completed",
    "finding_dismissed": "AI finding dismissed",
    "approved": "Assessment approved",
    "returned": "Returned for changes",
    "portal_case_pulled": "Case record read from agency portal",
    "portal_pull_failed": "Agency portal could not be read",
    "portal_draft_pushed": "Pre-filled form saved to agency portal",
    "portal_push_rejected": "Agency portal refused the pre-filled form",
    "portal_push_failed": "Agency portal could not be reached",
    "submitted_in_portal": "Worker submitted the form in agency portal",
}


def doc_label(doc_id: str) -> str:
    """Turn a document id such as "01-intake-note" into "Intake note" for citations."""
    words = [w for w in doc_id.split("-") if not w.isdigit()]
    return " ".join(words).capitalize() or doc_id


def when(value: datetime) -> str:
    """Dates in tables and notices, always UTC: "Nov 21, 2026 01:12"."""
    return f"{value:%b} {value.day}, {value:%Y %H:%M}"


TEMPLATES.env.filters["doc_label"] = doc_label
TEMPLATES.env.filters["when"] = when
TEMPLATES.env.globals["ACTION_LABELS"] = ACTION_LABELS
TEMPLATES.env.globals["AGENT_ACTORS"] = {DRAFTING_AGENT, QA_AGENT}


def get_store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


def get_runner(request: Request) -> CaseRunner:
    runner: CaseRunner = request.app.state.runner
    return runner


def get_portal_client(request: Request) -> PortalClient:
    return PortalClient(request.app.state.portal_http, request.app.state.portal_api_key)


PortalClientDep = Annotated[PortalClient, Depends(get_portal_client)]


def known_case(case_id: str) -> SyntheticCase:
    if case_id not in list_case_ids():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown case")
    return load_case(case_id)


StoreDep = Annotated[Store, Depends(get_store)]
CaseDep = Annotated[SyntheticCase, Depends(known_case)]


def back_to_case(case_id: str, tab: Tab = "draft") -> RedirectResponse:
    # 303 turns the browser's POST into a GET of the case page.
    url = f"/cases/{case_id}" if tab == "draft" else f"/cases/{case_id}?tab={tab}"
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def last_event(events: list[AuditEvent], action: str | None = None) -> AuditEvent | None:
    matching = [e for e in events if action is None or e.action == action]
    return matching[-1] if matching else None


async def html_or_json_error(request: Request, exc: Exception) -> Response:
    """Browsers get a readable error page; API clients keep FastAPI's JSON body."""
    if not isinstance(exc, StarletteHTTPException):  # registered only for this type
        raise exc
    if "text/html" not in request.headers.get("accept", ""):
        return await http_exception_handler(request, exc)
    return TEMPLATES.TemplateResponse(
        request,
        "error.html",
        {"status_code": exc.status_code, "detail": exc.detail, "user": None},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request, store: StoreDep, user: Annotated[User, Depends(current_user)]
) -> HTMLResponse:
    rows = []
    for case_id in list_case_ids():
        events = store.list_events(case_id)
        run = last_event(events, "run_started")
        rows.append(
            {
                "case": load_case(case_id),
                "record": store.get_case(case_id),
                "last_event": last_event(events),
                "run_by": run.actor if run else None,
            }
        )
    return TEMPLATES.TemplateResponse(request, "index.html", {"rows": rows, "user": user})


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def case_page(
    request: Request,
    case: CaseDep,
    store: StoreDep,
    user: Annotated[User, Depends(current_user)],
    tab: Tab = "draft",
    doc: str | None = None,
    page: int = 1,
) -> HTMLResponse:
    source = None
    if doc is not None:
        source = load_source_page(case.case_id, doc, page)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown source document or page")
    events = store.list_events(case.case_id)
    run = last_event(events, "run_started")
    context = {
        "case": case,
        "record": store.get_case(case.case_id),
        "events": events,
        "user": user,
        "tab": tab,
        "source": source,
        "source_docs": list_source_docs(case.case_id),
        "run_by": run.actor if run else None,
        "last_approved": last_event(events, "approved"),
        "last_returned": last_event(events, "returned"),
    }
    return TEMPLATES.TemplateResponse(request, "case.html", context)


@router.post("/cases/{case_id}/run")
def run(
    case: CaseDep,
    store: StoreDep,
    runner: Annotated[CaseRunner, Depends(get_runner)],
    portal: PortalClientDep,
    user: Annotated[User, Depends(require_role(CASEWORKER))],
) -> RedirectResponse:
    pull_case(store, portal, case.case_id, user)
    try:
        run_and_record(store, runner, case, user)
    except WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return back_to_case(case.case_id)


@router.post("/cases/{case_id}/approve")
def approve_draft(
    case: CaseDep,
    store: StoreDep,
    portal: PortalClientDep,
    user: Annotated[User, Depends(require_role(SUPERVISOR))],
) -> RedirectResponse:
    try:
        approve(store, case.case_id, user)
    except WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    # The worker reviews and submits it in the portal; we only save a draft there.
    push_approved_draft(store, portal, case, user)
    return back_to_case(case.case_id, "qa")


@router.post("/cases/{case_id}/portal/push")
def push_to_portal(
    case: CaseDep,
    store: StoreDep,
    portal: PortalClientDep,
    user: Annotated[User, Depends(require_role(SUPERVISOR))],
) -> RedirectResponse:
    """Retry sending an approved draft, for example after the portal was down."""
    try:
        push_approved_draft(store, portal, case, user)
    except PushError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return back_to_case(case.case_id, "audit")


@router.post("/cases/{case_id}/dismiss")
def dismiss(
    case: CaseDep,
    store: StoreDep,
    user: Annotated[User, Depends(require_role(SUPERVISOR))],
    item_id: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        dismiss_finding(store, case.case_id, user, item_id, reason)
    except WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return back_to_case(case.case_id, "qa")


@router.post("/cases/{case_id}/return")
def return_draft(
    case: CaseDep,
    store: StoreDep,
    user: Annotated[User, Depends(require_role(SUPERVISOR))],
    comment: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        return_for_changes(store, case.case_id, user, comment)
    except WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return back_to_case(case.case_id, "qa")


@router.get("/api/cases/{case_id}")
def case_json(
    case: CaseDep, store: StoreDep, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    record = store.get_case(case.case_id)
    return {
        "case": record.model_dump(mode="json") if record else None,
        "can_approve": bool(record and record.can_approve),
        "events": [e.model_dump(mode="json") for e in store.list_events(case.case_id)],
    }
