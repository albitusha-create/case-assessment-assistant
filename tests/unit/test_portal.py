from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from caa.config import get_settings
from caa.main import create_app
from caa.portal.store import (
    DomainPrefill,
    DraftIn,
    FormHeader,
    HeaderPrefill,
    PortalConflict,
    PortalStore,
    PortalValidationError,
    ReferenceNote,
    SourceRef,
    SubmittedEvent,
)
from caa.storage.store import MemoryStore

KEY = "test-portal-key"
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def portal() -> PortalStore:
    return PortalStore.seeded(today=date(2026, 11, 1))


def draft() -> DraftIn:
    return DraftIn(
        header=HeaderPrefill(
            assessment_type="initial",
            date_started=date(2026, 10, 5),
            information_sources=["external_records"],
            sources_detail="Intake Note; Primary Care Referral Letter",
        ),
        domains={
            "strengths": DomainPrefill(
                text="Describes herself as organized.",
                sources=[SourceRef(doc_id="01-intake-note", page=2)],
            ),
            "community_living": DomainPrefill(
                text="Staying with a friend since her lease ended in August.",
                sources=[SourceRef(doc_id="01-intake-note", page=1)],
            ),
        },
        references={
            "substance_use": [
                ReferenceNote(
                    text="Reports drinking two or three times a week.",
                    sources=[SourceRef(doc_id="01-intake-note", page=2)],
                )
            ]
        },
        ask_in_interview=["finances_benefits", "legal_status", "life_satisfaction"],
    )


# --- store rules -------------------------------------------------------------


def test_seeded_cases_have_due_dates_and_documents(portal: PortalStore) -> None:
    cases = portal.list_cases()
    assert {c.case_id for c in cases} == {"case-001", "case-002", "case-003", "case-004"}
    assert [c.assessment_due for c in cases] == sorted(c.assessment_due for c in cases)
    first = portal.get_case("case-001")
    assert first.assessment_type == "initial"
    assert first.assessment_due == date(2026, 11, 4)  # 30 calendar days from 2026-10-05
    assert portal.get_case("case-004").assessment_type == "update"
    assert all(portal.get_form(c.case_id).status == "not_started" for c in cases)


def test_prefill_saves_a_draft_with_sources(portal: PortalStore) -> None:
    form, replayed = portal.save_prefill("case-001", draft(), "assistant", "key-0001")
    assert not replayed
    assert form.status == "draft"
    assert form.prefilled_by == "assistant"
    assert form.domains["strengths"].origin == "assistant"
    assert form.domains["strengths"].sources[0].page == 2
    assert form.header.assessment_type == "initial"
    assert "substance_use" not in form.domains  # a reference, not a filled field


def test_same_idempotency_key_is_a_replay(portal: PortalStore) -> None:
    portal.save_prefill("case-001", draft(), "assistant", "key-0001")
    form, replayed = portal.save_prefill("case-001", draft(), "assistant", "key-0001")
    assert replayed
    assert form.status == "draft"


@pytest.mark.parametrize("domain", ["mental_health", "substance_use", "life_satisfaction"])
def test_clinician_and_self_rated_domains_cannot_be_prefilled(
    portal: PortalStore, domain: str
) -> None:
    bad = draft()
    bad.domains[domain] = DomainPrefill(text="Something.")
    with pytest.raises(PortalValidationError, match=domain):
        portal.save_prefill("case-001", bad, "assistant", "key-0002")


def test_unknown_domain_is_refused(portal: PortalStore) -> None:
    bad = draft()
    bad.domains["risk_level"] = DomainPrefill(text="High.")
    with pytest.raises(PortalValidationError, match="Unknown domain"):
        portal.save_prefill("case-001", bad, "assistant", "key-0003")


def test_prefill_never_overwrites_worker_edits(portal: PortalStore) -> None:
    form, _ = portal.save_prefill("case-001", draft(), "assistant", "key-0001")
    portal.worker_save("case-001", "casey", form.header, {"strengths": "Organized and punctual."})
    with pytest.raises(PortalConflict, match="edited"):
        portal.save_prefill("case-001", draft(), "assistant", "key-0004")


def test_submit_needs_attestation_and_reports_changes(portal: PortalStore) -> None:
    events: list[SubmittedEvent] = []
    portal.listeners.append(events.append)
    form, _ = portal.save_prefill("case-001", draft(), "assistant", "key-0001")
    portal.worker_save(
        "case-001",
        "casey",
        form.header,
        {
            "strengths": "Organized and punctual.",
            "community_living": form.domains["community_living"].text,
        },
    )
    with pytest.raises(PortalValidationError, match="attestation"):
        portal.submit("case-001", "casey", attested=False)

    event = portal.submit("case-001", "casey", attested=True)
    assert event.prefilled_domains == 2
    assert event.changed_by_worker == 1
    assert events == [event]
    assert portal.get_form("case-001").header.date_completed is not None
    with pytest.raises(PortalConflict, match="submitted"):
        portal.save_prefill("case-001", draft(), "assistant", "key-0005")


def test_worker_save_without_changes_is_not_an_edit(portal: PortalStore) -> None:
    form, _ = portal.save_prefill("case-001", draft(), "assistant", "key-0001")
    same = {d: e.text for d, e in form.domains.items()}
    portal.worker_save("case-001", "casey", FormHeader(**form.header.model_dump()), same)
    assert not portal.get_form("case-001").worker_edited


# --- REST API ----------------------------------------------------------------


@pytest.fixture
def client(portal: PortalStore, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("PORTAL_API_KEY", KEY)
    get_settings.cache_clear()
    yield TestClient(create_app(store=MemoryStore(), portal=portal))
    get_settings.cache_clear()


def test_api_requires_the_key(client: TestClient) -> None:
    assert client.get("/portal/api/v1/cases").status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert client.get("/portal/api/v1/cases", headers=wrong).status_code == 401
    assert client.get("/portal/api/v1/cases", headers=AUTH).status_code == 200


def test_api_reads_cases_schema_and_documents(client: TestClient) -> None:
    cases = client.get("/portal/api/v1/cases", headers=AUTH).json()
    assert cases[0]["form_status"] == "not_started"
    case = client.get("/portal/api/v1/cases/case-002", headers=AUTH).json()
    assert [d["doc_id"] for d in case["documents"]] == ["01-intake-note", "02-school-record"]
    schema = client.get("/portal/api/v1/forms/core-assessment/schema", headers=AUTH).json()
    assert {d["id"] for d in schema["domains"] if not d["assistant_may_prefill"]} == {
        "life_satisfaction",
        "mental_health",
        "substance_use",
        "trauma_stressors",
    }
    pdf = client.get("/portal/api/v1/cases/case-002/documents/01-intake-note", headers=AUTH)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"


@pytest.mark.parametrize("doc_id", ["../case-001/01-intake-note", "nope", "..%2Fcase.json"])
def test_api_serves_only_listed_documents(client: TestClient, doc_id: str) -> None:
    url = f"/portal/api/v1/cases/case-002/documents/{doc_id}"
    assert client.get(url, headers=AUTH).status_code == 404


def test_api_save_draft_status_codes(client: TestClient) -> None:
    url = "/portal/api/v1/cases/case-001/assessment/draft"
    body = draft().model_dump(mode="json")
    assert client.put(url, json=body, headers=AUTH).status_code == 422  # no Idempotency-Key
    headers = {**AUTH, "Idempotency-Key": "case-001:v1"}
    saved = client.put(url, json=body, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["status"] == "draft"
    assert client.put(url, json=body, headers=headers).status_code == 200  # replay

    bad = {**body, "domains": {"mental_health": {"text": "x"}}}
    other = {**AUTH, "Idempotency-Key": "case-001:v2"}
    assert client.put(url, json=bad, headers=other).status_code == 422
    assert (
        client.put(
            "/portal/api/v1/cases/case-999/assessment/draft", json=body, headers=other
        ).status_code
        == 404
    )


def test_api_has_no_submit_operation(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    portal_ops = [p for p in paths if p.startswith("/portal/api/v1")]
    assert portal_ops
    assert not any("submit" in p for p in portal_ops)


# --- pages -------------------------------------------------------------------


def test_worker_pages_render_and_submit(client: TestClient) -> None:
    client.put(
        "/portal/api/v1/cases/case-001/assessment/draft",
        json=draft().model_dump(mode="json"),
        headers={**AUTH, "Idempotency-Key": "case-001:v1"},
    )
    assert "My Caseload" in client.get("/portal").text
    assert "Attached Documents" in client.get("/portal/cases/case-001").text
    page = client.get("/portal/cases/case-001/assessment").text
    assert "Pre-filled by Case Assessment Assistant" in page
    assert "Intake Note, p. 2" in page
    assert "Ask in the interview" in page

    fields = {
        "assessment_type": "initial",
        "date_started": "2026-10-05",
        "information_sources": "external_records",
        "sources_detail": "Intake Note; Primary Care Referral Letter",
        "domain_strengths": "Describes herself as organized.",
        "domain_community_living": "Staying with a friend since her lease ended in August.",
        "action": "submit",
    }
    no_attest = client.post("/portal/cases/case-001/assessment", data=fields)
    assert "attestation" in no_attest.text
    done = client.post("/portal/cases/case-001/assessment", data={**fields, "attest": "on"})
    assert "Assessment submitted." in done.text
    assert "Submit Assessment" not in done.text
