import base64
import json

import pytest
from fastapi.testclient import TestClient

from caa.agents.orchestrator import DraftResult
from caa.agents.pipeline import CaseRun
from caa.api.auth import PRINCIPAL_HEADER, parse_principal
from caa.extraction.schema import ExtractionResult
from caa.main import create_app
from caa.models import Draft
from caa.qa.report import CheckResult, QAReport
from caa.storage.store import MemoryStore
from caa.synthetic import SyntheticCase


def report(blocking_fails: bool) -> QAReport:
    return QAReport(
        case_id="case-002",
        checklist_version="1.0.0",
        results=[
            CheckResult(
                item_id="conflicts_named",
                description="Conflicts are named.",
                checked_by="agent",
                severity="blocking",
                passed=not blocking_fails,
                findings=["Aunt vs grandmother."] if blocking_fails else [],
            )
        ],
        acknowledged_gaps=[],
    )


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def make_client(store: MemoryStore, draft: Draft, blocking_fails: bool = False) -> TestClient:
    def runner(case: SyntheticCase) -> CaseRun:
        facts = ExtractionResult(case_id=case.case_id, facts=[], rejected=[])
        drafted = DraftResult(
            draft=draft.model_copy(update={"case_id": case.case_id}), dropped_citations=[]
        )
        return CaseRun(facts=facts, drafted=drafted, report=report(blocking_fails))

    return TestClient(create_app(store=store, runner=runner))


def principal(name: str, *roles: str) -> dict[str, str]:
    claims = [{"typ": "name", "val": name}] + [{"typ": "roles", "val": r} for r in roles]
    encoded = base64.b64encode(json.dumps({"claims": claims}).encode()).decode()
    return {PRINCIPAL_HEADER: encoded}


CASEWORKER = principal("casey", "Caseworker")
SUPERVISOR = principal("sam", "Supervisor")


def test_parse_easy_auth_principal() -> None:
    user = parse_principal(SUPERVISOR[PRINCIPAL_HEADER])
    assert (user.name, user.roles) == ("sam", {"Supervisor"})


def test_pages_render(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    assert "case-002" in client.get("/").text
    assert client.get("/cases/case-002").status_code == 200
    assert client.get("/cases/case-999").status_code == 404


def test_run_then_approve_writes_the_audit_trail(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)

    response = client.post("/cases/case-002/run", headers=CASEWORKER, follow_redirects=False)
    assert response.status_code == 303
    assert store.cases["case-002"].status == "in_review"

    assert client.post("/cases/case-002/approve", headers=SUPERVISOR).status_code == 200
    assert store.cases["case-002"].status == "approved"

    events = client.get("/api/cases/case-002", headers=SUPERVISOR).json()["events"]
    assert [(e["actor"], e["action"]) for e in events] == [
        ("casey", "run_started"),
        ("caa-drafting", "drafted"),
        ("caa-qa", "qa_completed"),
        ("sam", "approved"),
    ]


def test_blocking_qa_item_prevents_approval(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft, blocking_fails=True)
    client.post("/cases/case-002/run", headers=CASEWORKER)

    response = client.post("/cases/case-002/approve", headers=SUPERVISOR)

    assert response.status_code == 409
    assert "conflicts_named" in response.json()["detail"]
    assert store.cases["case-002"].status == "in_review"


def test_roles_are_enforced(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    assert client.post("/cases/case-002/run", headers=SUPERVISOR).status_code == 403
    client.post("/cases/case-002/run", headers=CASEWORKER)
    assert client.post("/cases/case-002/approve", headers=CASEWORKER).status_code == 403


def test_return_needs_a_comment_and_is_logged(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    client.post("/cases/case-002/run", headers=CASEWORKER)

    assert (
        client.post("/cases/case-002/return", headers=SUPERVISOR, data={"comment": " "}).status_code
        == 409
    )
    client.post("/cases/case-002/return", headers=SUPERVISOR, data={"comment": "Confirm guardian."})

    assert store.cases["case-002"].status == "returned"
    assert store.events[-1].details == {"comment": "Confirm guardian."}


def test_approve_without_a_draft_is_refused(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    assert client.post("/cases/case-002/approve", headers=SUPERVISOR).status_code == 409


def test_outside_local_a_missing_principal_is_401(
    store: MemoryStore, complete_draft: Draft, monkeypatch: pytest.MonkeyPatch
) -> None:
    from caa.config import Settings, get_settings

    client = make_client(store, complete_draft)
    client.app.dependency_overrides[get_settings] = lambda: Settings(environment="azure")  # type: ignore[attr-defined]
    assert client.get("/").status_code == 401
