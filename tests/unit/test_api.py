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


def test_principal_prefers_display_name_over_email() -> None:
    claims = [
        {"typ": "preferred_username", "val": "person@example.com"},
        {"typ": "name", "val": "Pat Doe"},
    ]
    header = base64.b64encode(
        json.dumps({"claims": claims, "name_typ": "preferred_username"}).encode()
    ).decode()
    assert parse_principal(header).name == "Pat Doe"


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


def rule_blocked_report() -> QAReport:
    return QAReport(
        case_id="case-002",
        checklist_version="1.0.0",
        results=[
            CheckResult(
                item_id="no_determinations",
                description="No determinations.",
                checked_by="rule",
                severity="blocking",
                passed=False,
                findings=['"is high risk" in summary'],
            )
        ],
        acknowledged_gaps=[],
    )


def test_supervisor_can_dismiss_an_agent_finding_then_approve(
    store: MemoryStore, complete_draft: Draft
) -> None:
    client = make_client(store, complete_draft, blocking_fails=True)
    client.post("/cases/case-002/run", headers=CASEWORKER)

    form = {
        "item_id": "conflicts_named",
        "reason": "Both versions are cited in Current functioning.",
    }
    assert client.post("/cases/case-002/dismiss", headers=SUPERVISOR, data=form).status_code == 200
    assert client.post("/cases/case-002/approve", headers=SUPERVISOR).status_code == 200

    actions = [(e.action, e.details) for e in store.events[-2:]]
    assert actions[0][0] == "finding_dismissed"
    assert actions[0][1]["reason"] == form["reason"]
    assert actions[1] == ("approved", {"dismissed_items": ["conflicts_named"]})


def test_dismiss_needs_a_reason_and_the_supervisor_role(
    store: MemoryStore, complete_draft: Draft
) -> None:
    client = make_client(store, complete_draft, blocking_fails=True)
    client.post("/cases/case-002/run", headers=CASEWORKER)
    form = {"item_id": "conflicts_named", "reason": ""}
    assert client.post("/cases/case-002/dismiss", headers=SUPERVISOR, data=form).status_code == 409
    form["reason"] = "Fine."
    assert client.post("/cases/case-002/dismiss", headers=CASEWORKER, data=form).status_code == 403


def test_rule_findings_cannot_be_dismissed(store: MemoryStore, complete_draft: Draft) -> None:
    def runner(case: SyntheticCase) -> CaseRun:
        facts = ExtractionResult(case_id=case.case_id, facts=[], rejected=[])
        drafted = DraftResult(draft=complete_draft, dropped_citations=[])
        return CaseRun(facts=facts, drafted=drafted, report=rule_blocked_report())

    client = TestClient(create_app(store=store, runner=runner))
    client.post("/cases/case-002/run", headers=CASEWORKER)
    form = {"item_id": "no_determinations", "reason": "Looks fine to me."}

    response = client.post("/cases/case-002/dismiss", headers=SUPERVISOR, data=form)

    assert response.status_code == 409
    assert "cannot be dismissed" in response.json()["detail"]
    assert client.post("/cases/case-002/approve", headers=SUPERVISOR).status_code == 409


def test_page_shows_dismiss_form_for_agent_findings(
    store: MemoryStore, complete_draft: Draft
) -> None:
    client = make_client(store, complete_draft, blocking_fails=True)
    client.post("/cases/case-002/run", headers=CASEWORKER)
    page = client.get("/cases/case-002?tab=qa", headers=SUPERVISOR).text
    assert 'action="/cases/case-002/dismiss"' in page
    assert "AI reviewer findings" in page
    assert "Approval blocked by 1 item" in page


def test_dismiss_and_return_go_back_to_the_qa_tab(
    store: MemoryStore, complete_draft: Draft
) -> None:
    client = make_client(store, complete_draft, blocking_fails=True)
    client.post("/cases/case-002/run", headers=CASEWORKER)

    response = client.post(
        "/cases/case-002/dismiss",
        headers=SUPERVISOR,
        data={"item_id": "conflicts_named", "reason": "Same fact, different words."},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/cases/case-002?tab=qa"
    assert "Same fact, different words." in client.get("/cases/case-002?tab=qa").text

    client.post("/cases/case-002/return", headers=SUPERVISOR, data={"comment": "Confirm guardian."})
    page = client.get("/cases/case-002", headers=SUPERVISOR).text
    assert "Returned for changes" in page
    assert "Confirm guardian." in page


def test_doc_label_reads_like_a_title() -> None:
    from caa.api.routes import doc_label

    assert doc_label("02-home-health-note") == "Home health note"


def test_citation_opens_the_cited_source_page(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    client.post("/cases/case-003/run", headers=CASEWORKER)
    page = client.get("/cases/case-003?doc=01-intake-note&page=2").text
    assert "Intake note, page 2 of 2" in page
    assert "retired bus mechanic" in page
    assert client.get("/cases/case-003?doc=../case.json&page=1").status_code == 404
    assert client.get("/cases/case-003?doc=01-intake-note&page=9").status_code == 404


def test_browsers_get_an_error_page_and_api_clients_get_json(
    store: MemoryStore, complete_draft: Draft
) -> None:
    client = make_client(store, complete_draft)
    html = client.get("/cases/case-999", headers={"accept": "text/html"})
    assert html.status_code == 404
    assert "Back to cases" in html.text
    assert client.get("/cases/case-999").json() == {"detail": "Unknown case"}
