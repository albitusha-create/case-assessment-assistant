"""Our app and the mock agency portal, end to end over the portal's REST API."""

import httpx
import pytest
from fastapi.testclient import TestClient

from caa.integrations.form_mapping import draft_to_form
from caa.integrations.portal_client import PortalClient
from caa.models import GAP_ELEMENT, Claim, Draft
from caa.portal.form import SCHEMA
from caa.portal.store import PortalStore
from caa.portal.webhooks import EVENTS_PATH, SIGNATURE_HEADER
from caa.storage.store import MemoryStore
from caa.synthetic import load_case
from tests.unit.test_api import CASEWORKER, SUPERVISOR, make_client


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


def actions(store: MemoryStore, case_id: str = "case-001") -> list[str]:
    return [e.action for e in store.list_events(case_id)]


# --- mapping -----------------------------------------------------------------


def test_mapping_fills_worker_domains_and_never_clinical_ones(complete_draft: Draft) -> None:
    case = PortalStore.seeded().get_case("case-001")
    form = draft_to_form(complete_draft, case, SCHEMA, load_case("case-001").start_date)

    assert set(form.domains) == {
        "strengths",
        "basic_needs",
        "community_living",
        "social_network_family",
        "employment_education",
        "physical_health",
    }
    assert set(form.references) == {"mental_health", "substance_use"}
    assert not {"mental_health", "substance_use", "trauma_stressors"} & set(form.domains)
    assert form.ask_in_interview == ["life_satisfaction", "finances_benefits", "legal_status"]
    assert form.header.assessment_type == "initial"
    assert form.header.information_sources == []  # the worker ticks these
    social = form.domains["social_network_family"]
    assert "family_social_history" in social.text and "natural_supports" in social.text
    assert social.sources  # every pre-filled domain carries its citations


def test_mapping_skips_gap_statements_and_uncited_claims(complete_draft: Draft) -> None:
    draft = complete_draft.model_copy(deep=True)
    draft.sections[0].claims.append(
        Claim(text="No finances documented.", elements=[GAP_ELEMENT, "strengths"])
    )
    case = PortalStore.seeded().get_case("case-001")
    form = draft_to_form(draft, case, SCHEMA, load_case("case-001").start_date)
    assert "No finances documented." not in form.domains["strengths"].text


# --- end to end --------------------------------------------------------------


def approve_case(client: TestClient, case_id: str = "case-001") -> None:
    assert client.post(f"/cases/{case_id}/run", headers=CASEWORKER).status_code == 200
    assert client.post(f"/cases/{case_id}/approve", headers=SUPERVISOR).status_code == 200


def test_approval_saves_a_prefilled_draft_the_worker_submits(
    store: MemoryStore, complete_draft: Draft
) -> None:
    client = make_client(store, complete_draft)
    approve_case(client)
    assert actions(store)[0] == "portal_case_pulled"
    assert actions(store)[-1] == "portal_draft_pushed"

    portal: PortalStore = client.app.state.portal  # type: ignore[attr-defined]
    form = portal.get_form("case-001")
    assert form.status == "draft"
    assert form.prefilled_by == "Case Assessment Assistant"
    assert "strengths" in form.domains

    # The worker edits one domain and submits in the portal.
    fields = {f"domain_{d}": e.text for d, e in form.domains.items()}
    fields |= {"domain_strengths": "Organized; finished counseling in 2024.", "action": "submit"}
    fields |= {"assessment_type": "initial", "attest": "on"}
    page = client.post("/portal/cases/case-001/assessment", data=fields)
    assert "Assessment submitted." in page.text

    submitted = store.list_events("case-001")[-1]
    assert submitted.action == "submitted_in_portal"
    assert submitted.actor == "agency-portal"
    assert submitted.details["changed_by_worker"] == 1
    assert submitted.details["prefilled_domains"] == 6


def test_portal_refuses_to_overwrite_worker_edits(
    store: MemoryStore, complete_draft: Draft
) -> None:
    client = make_client(store, complete_draft)
    approve_case(client)
    portal: PortalStore = client.app.state.portal  # type: ignore[attr-defined]
    form = portal.get_form("case-001")
    portal.worker_save("case-001", "casey", form.header, {"strengths": "Typed by the worker."})

    approve_case(client)  # a second run and approval
    assert actions(store)[-1] == "portal_push_rejected"
    assert portal.get_form("case-001").domains["strengths"].text == "Typed by the worker."


def test_retrying_a_push_is_idempotent(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    approve_case(client)
    response = client.post("/cases/case-001/portal/push", headers=SUPERVISOR)
    assert response.status_code == 200
    pushes = [e for e in store.list_events("case-001") if e.action == "portal_draft_pushed"]
    assert len(pushes) == 2
    assert pushes[0].details["idempotency_key"] == pushes[1].details["idempotency_key"]


def test_push_needs_an_approved_draft(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    client.post("/cases/case-001/run", headers=CASEWORKER)
    assert client.post("/cases/case-001/portal/push", headers=SUPERVISOR).status_code == 409
    assert client.post("/cases/case-001/portal/push", headers=CASEWORKER).status_code == 403


def test_portal_outage_never_blocks_our_workflow(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    client.app.state.portal_http = httpx.Client(base_url="http://127.0.0.1:9", timeout=1)  # type: ignore[attr-defined]
    approve_case(client)
    assert store.cases["case-001"].status == "approved"
    assert actions(store)[0] == "portal_pull_failed"
    assert actions(store)[-1] == "portal_push_failed"


def test_webhook_needs_a_valid_signature(store: MemoryStore, complete_draft: Draft) -> None:
    client = make_client(store, complete_draft)
    body = b'{"case_id": "case-001"}'
    response = client.post(EVENTS_PATH, content=body, headers={SIGNATURE_HEADER: "sha256=0"})
    assert response.status_code == 401
    assert actions(store) == []


def test_client_sends_no_auth_header_without_a_key() -> None:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, json=[])

    http = httpx.Client(base_url="http://portal", transport=httpx.MockTransport(handler))
    PortalClient(http, "").list_cases()
    PortalClient(http, "k3y").list_cases()
    assert "authorization" not in seen[0]
    assert seen[1]["authorization"] == "Bearer k3y"
