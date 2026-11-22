"""The assistant inside the agency portal: section checks, their API and audit."""

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from caa.assist.section_check import (
    NOT_REPORTED,
    ModelDetail,
    ModelItem,
    ModelOutput,
    ModelSuggestion,
    SectionCheck,
    Source,
    Suggestion,
    assist_allowed,
    check_section,
    domain_elements,
)
from caa.main import create_app
from caa.portal.form import SCHEMA, Domain
from caa.retrieval.search import SearchHit
from caa.rules import Criteria
from caa.storage.store import MemoryStore
from tests.unit.test_api import CASEWORKER, SUPERVISOR

STRENGTHS = SCHEMA.domain("strengths")
BASIC_NEEDS = SCHEMA.domain("basic_needs")
assert STRENGTHS is not None and BASIC_NEEDS is not None

CHUNKS = [
    SearchHit(
        chunk_id="case-001-01-intake-note-p1",
        case_id="case-001",
        doc_id="01-intake-note",
        page=1,
        section="",
        text="Dana enjoys painting and volunteers at the library.",
        score=1.0,
    )
]


class FakeResponses:
    def __init__(self, output: ModelOutput) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.output)


def fake_client(output: ModelOutput) -> Any:
    return SimpleNamespace(responses=FakeResponses(output))


def run(criteria: Criteria, output: ModelOutput, text: str, domain: Domain = STRENGTHS) -> Any:
    client = fake_client(output)
    result = check_section(client, "chat", criteria, "case-001", domain, text, CHUNKS)
    return result, client.responses.calls


def test_only_worker_sections_the_assistant_may_prefill() -> None:
    allowed = {d.id for d in SCHEMA.domains if assist_allowed(d)}
    assert "strengths" in allowed
    assert allowed.isdisjoint({"mental_health", "substance_use", "trauma_stressors"})
    assert "life_satisfaction" not in allowed  # the person's own words and self-rating


def test_clinical_section_is_refused_in_code(criteria: Criteria) -> None:
    mental_health = SCHEMA.domain("mental_health")
    assert mental_health is not None
    with pytest.raises(ValueError):
        run(criteria, ModelOutput(items=[], suggestions=[]), "text", mental_health)


def test_elements_come_from_the_form_mapping(criteria: Criteria) -> None:
    assert set(domain_elements(criteria, "basic_needs")) == {
        "client_stated_needs",
        "living_situation",
    }


def test_sources_resolved_in_code_and_foreign_chunks_dropped(criteria: Criteria) -> None:
    output = ModelOutput(
        items=[
            ModelItem(
                item_id="claims_supported",
                passed=False,
                details=[
                    ModelDetail(
                        text='"paints daily" is not in the records.',
                        chunk_ids=["case-001-01-intake-note-p1", "case-002-x-p1"],
                    )
                ],
            )
        ],
        suggestions=[
            ModelSuggestion(text="Volunteers at the library.", chunk_id=CHUNKS[0].chunk_id),
            ModelSuggestion(text="From another case.", chunk_id="case-002-x-p1"),
        ],
    )
    result, _ = run(criteria, output, "Dana paints daily.")
    supported = next(r for r in result.results if r.item_id == "claims_supported")
    assert not supported.passed
    assert supported.findings[0].sources == [Source(doc_id="01-intake-note", page=1)]
    assert result.suggestions == [
        Suggestion(
            text="Volunteers at the library.", source=Source(doc_id="01-intake-note", page=1)
        )
    ]
    assert result.dropped_citations == 2


def test_unreported_item_fails_closed(criteria: Criteria) -> None:
    result, _ = run(criteria, ModelOutput(items=[], suggestions=[]), "Dana is kind.")
    judged = [r for r in result.results if r.checked_by == "agent"]
    assert judged and all(not r.passed for r in judged)
    assert judged[0].findings[0].text == NOT_REPORTED


def test_strengths_item_only_on_the_strengths_section(criteria: Criteria) -> None:
    on_strengths, _ = run(criteria, ModelOutput(items=[], suggestions=[]), "x")
    on_needs, calls = run(criteria, ModelOutput(items=[], suggestions=[]), "x", BASIC_NEEDS)
    assert "strengths_included" in {r.item_id for r in on_strengths.results}
    assert "strengths_included" not in {r.item_id for r in on_needs.results}
    assert "strengths_included" not in calls[0]["input"]


def test_determination_wording_is_a_rule_check(criteria: Criteria) -> None:
    result, _ = run(criteria, ModelOutput(items=[], suggestions=[]), "She is eligible for help.")
    rule = next(r for r in result.results if r.item_id == "no_determinations")
    assert (rule.checked_by, rule.passed) == ("rule", False)
    assert '"is eligible"' in rule.findings[0].text


def test_input_carries_text_and_case_chunks(criteria: Criteria) -> None:
    _, calls = run(criteria, ModelOutput(items=[], suggestions=[]), "Dana likes art.")
    assert "Dana likes art." in calls[0]["input"]
    assert CHUNKS[0].chunk_id in calls[0]["input"]


# ---------------------------------------------------------------- API


def stub_checker(case_id: str, domain: Domain, text: str) -> SectionCheck:
    return SectionCheck(
        case_id=case_id,
        domain_id=domain.id,
        results=[],
        suggestions=[
            Suggestion(text="Volunteers weekly.", source=Source(doc_id="01-intake-note", page=1))
        ],
    )


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def client(store: MemoryStore) -> TestClient:
    app = create_app(store=store, section_checker=stub_checker)
    test_client = TestClient(app)
    app.state.portal_http = test_client
    return test_client


def test_lists_checkable_sections(client: TestClient) -> None:
    body = client.get("/api/assist/cases/case-001/sections", headers=CASEWORKER).json()
    ids = [s["id"] for s in body["sections"]]
    assert "strengths" in ids and "mental_health" not in ids


def test_check_returns_results_and_logs_the_check(client: TestClient, store: MemoryStore) -> None:
    response = client.post(
        "/api/assist/cases/case-001/sections/strengths/check",
        json={"text": "Dana likes art."},
        headers=CASEWORKER,
    )
    assert response.status_code == 200
    assert response.json()["suggestions"][0]["text"] == "Volunteers weekly."
    [event] = store.list_events("case-001")
    assert (event.action, event.actor) == ("portal_section_checked", "casey")
    assert event.details["section"] == "Strengths"
    assert event.details["suggestions"] == 1


def test_clinical_section_check_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/assist/cases/case-001/sections/mental_health/check",
        json={"text": "x"},
        headers=CASEWORKER,
    )
    assert response.status_code == 409


def test_check_needs_the_caseworker_role(client: TestClient) -> None:
    response = client.post(
        "/api/assist/cases/case-001/sections/strengths/check",
        json={"text": "x"},
        headers=SUPERVISOR,
    )
    assert response.status_code == 403


def test_unknown_case_and_section(client: TestClient) -> None:
    url = "/api/assist/cases/{}/sections/{}/check"
    assert (
        client.post(
            url.format("case-999", "strengths"), json={"text": "x"}, headers=CASEWORKER
        ).status_code
        == 404
    )
    assert (
        client.post(
            url.format("case-001", "nope"), json={"text": "x"}, headers=CASEWORKER
        ).status_code
        == 404
    )


def test_inserted_suggestion_is_logged(client: TestClient, store: MemoryStore) -> None:
    response = client.post(
        "/api/assist/cases/case-001/sections/strengths/inserted",
        json={"doc_id": "01-intake-note", "page": 1},
        headers=CASEWORKER,
    )
    assert response.status_code == 204
    [event] = store.list_events("case-001")
    assert event.action == "portal_suggestion_inserted"
    assert event.details == {"section": "Strengths", "source": "01-intake-note, page 1"}


def test_portal_form_loads_the_assistant_script(client: TestClient) -> None:
    page = client.get("/portal/cases/case-001/assessment", headers=CASEWORKER).text
    assert 'src="/static/portal-assistant.js" data-case-id="case-001"' in page
