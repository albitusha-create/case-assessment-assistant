"""HTTP routes: HTML pages for people, plus one JSON endpoint for integrations.

Pages use plain HTML forms that post and redirect back to the case page, so
there is no front-end framework to explain.
"""

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from caa.api.auth import CASEWORKER, SUPERVISOR, User, current_user, require_role
from caa.api.workflow import (
    CaseRunner,
    WorkflowError,
    approve,
    dismiss_finding,
    return_for_changes,
    run_and_record,
)
from caa.storage.store import Store
from caa.synthetic import SyntheticCase, list_case_ids, load_case

TEMPLATES = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "web" / "templates")
router = APIRouter()


def get_store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


def get_runner(request: Request) -> CaseRunner:
    runner: CaseRunner = request.app.state.runner
    return runner


def known_case(case_id: str) -> SyntheticCase:
    if case_id not in list_case_ids():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown case")
    return load_case(case_id)


StoreDep = Annotated[Store, Depends(get_store)]
CaseDep = Annotated[SyntheticCase, Depends(known_case)]


def back_to_case(case_id: str) -> RedirectResponse:
    # 303 turns the browser's POST into a GET of the case page.
    return RedirectResponse(f"/cases/{case_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request, store: StoreDep, user: Annotated[User, Depends(current_user)]
) -> HTMLResponse:
    cases = [(case_id, store.get_case(case_id)) for case_id in list_case_ids()]
    return TEMPLATES.TemplateResponse(request, "index.html", {"cases": cases, "user": user})


@router.get("/cases/{case_id}", response_class=HTMLResponse)
def case_page(
    request: Request, case: CaseDep, store: StoreDep, user: Annotated[User, Depends(current_user)]
) -> HTMLResponse:
    context = {
        "case": case,
        "record": store.get_case(case.case_id),
        "events": store.list_events(case.case_id),
        "user": user,
        "today": date.today(),
    }
    return TEMPLATES.TemplateResponse(request, "case.html", context)


@router.post("/cases/{case_id}/run")
def run(
    case: CaseDep,
    store: StoreDep,
    runner: Annotated[CaseRunner, Depends(get_runner)],
    user: Annotated[User, Depends(require_role(CASEWORKER))],
) -> RedirectResponse:
    try:
        run_and_record(store, runner, case, user)
    except WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return back_to_case(case.case_id)


@router.post("/cases/{case_id}/approve")
def approve_draft(
    case: CaseDep, store: StoreDep, user: Annotated[User, Depends(require_role(SUPERVISOR))]
) -> RedirectResponse:
    try:
        approve(store, case.case_id, user)
    except WorkflowError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return back_to_case(case.case_id)


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
    return back_to_case(case.case_id)


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
    return back_to_case(case.case_id)


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
