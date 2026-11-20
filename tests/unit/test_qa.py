import json
from datetime import date

from caa.agents.definitions import QA_AGENT, qa_definition
from caa.agents.orchestrator import agent_results, format_qa_input, review_draft
from caa.agents.schema import QAFinding, QAOutput
from caa.agents.tool_dispatch import dispatch, make_qa_tools
from caa.models import Claim, Draft
from caa.qa.report import CheckResult
from caa.qa.rule_checks import run_rule_checks
from caa.retrieval.search import SearchHit
from caa.rules import Criteria
from caa.rules.criteria import ChecklistItem
from tests.unit.test_agents import FakeAgentsOpenAI, answer

START = date(2026, 10, 12)  # initial assessment: due 30 calendar days later
ON_TIME = date(2026, 10, 20)


def chunk_ids(draft: Draft) -> set[str]:
    return {c.chunk_id for s in draft.sections for claim in s.claims for c in claim.citations}


def by_id(results: list[CheckResult]) -> dict[str, CheckResult]:
    return {r.item_id: r for r in results}


def test_complete_draft_passes_every_rule_item(criteria: Criteria, complete_draft: Draft) -> None:
    results, _ = run_rule_checks(
        criteria, complete_draft, chunk_ids(complete_draft), START, ON_TIME
    )
    rule_items = [i.id for i in criteria.checklist.items if i.checked_by == "rule"]
    assert [r.item_id for r in results] == rule_items
    assert all(r.passed for r in results)


def test_rule_failures_carry_readable_findings(criteria: Criteria, complete_draft: Draft) -> None:
    complete_draft.sections[0].claims.append(Claim(text="Jordan is high risk.", elements=[]))
    results, _ = run_rule_checks(
        criteria, complete_draft, chunk_ids(complete_draft), START, date(2026, 12, 1)
    )
    checks = by_id(results)
    assert not checks["no_determinations"].passed
    assert "is high risk" in checks["no_determinations"].findings[0]
    assert not checks["citation_coverage"].passed  # the new claim has no citation
    assert checks["completed_by_due_date"].findings == ["Overdue: due 2026-11-11, 20 days ago"]
    assert checks["completed_by_due_date"].severity == "warning"


def test_unknown_chunks_fail_citations_resolve(criteria: Criteria, complete_draft: Draft) -> None:
    results, _ = run_rule_checks(criteria, complete_draft, set(), START, ON_TIME)
    assert not by_id(results)["citations_resolve"].passed


def agent_items(criteria: Criteria) -> list[ChecklistItem]:
    return [i for i in criteria.checklist.items if i.checked_by == "agent"]


def test_agent_results_fail_closed_and_take_severity_from_checklist(criteria: Criteria) -> None:
    output = QAOutput(
        findings=[
            QAFinding(item_id="claims_supported", passed=True, details=["looked fine"]),
            QAFinding(item_id="conflicts_named", passed=False, details=["Guardian conflict."]),
        ]
    )
    results = by_id(agent_results(agent_items(criteria), output))
    assert results["claims_supported"].passed
    assert results["claims_supported"].findings == []
    assert results["conflicts_named"].findings == ["Guardian conflict."]
    assert results["conflicts_named"].severity == "blocking"
    skipped = results["safety_concerns_carried"]
    assert not skipped.passed
    assert skipped.findings == ["The QA agent did not report on this item."]


def test_qa_get_chunks_only_returns_this_case() -> None:
    hit = SearchHit(
        chunk_id="c1", case_id="case-002", doc_id="d", page=1, section="", text="t", score=1.0
    )
    tools = make_qa_tools([hit], search=lambda q: [])
    result = json.loads(dispatch(tools, "get_chunks", '{"chunk_ids": ["c1", "case-001_x"]}'))
    assert result[0]["text"] == "t"
    assert result[1] == {"chunk_id": "case-001_x", "error": "not found in this case"}


def test_qa_definition_tools_and_input(criteria: Criteria, complete_draft: Draft) -> None:
    assert [t.name for t in qa_definition("m").tools] == ["get_chunks", "search_case_documents"]
    text = format_qa_input("case-002", agent_items(criteria), complete_draft)
    assert "- conflicts_named:" in text
    assert "chunks: referral_source-chunk" in text


def test_review_draft_merges_rule_and_agent_results(
    criteria: Criteria, complete_draft: Draft
) -> None:
    findings = [
        {"item_id": i.id, "passed": i.id != "conflicts_named", "details": ["Aunt vs grandmother."]}
        for i in agent_items(criteria)
    ]
    fake = FakeAgentsOpenAI([answer(json.dumps({"findings": findings}))])
    hits = [
        SearchHit(chunk_id=c, case_id="case-002", doc_id="d", page=1, section="", text="t", score=1)
        for c in chunk_ids(complete_draft)
    ]

    report = review_draft(fake, criteria, complete_draft, hits, lambda q: [], START, ON_TIME)

    assert [r.item_id for r in report.results] == [i.id for i in criteria.checklist.items]
    assert [r.item_id for r in report.blocking_failures] == ["conflicts_named"]
    assert not report.can_approve
    assert fake.requests[0]["extra_body"]["agent_reference"]["name"] == QA_AGENT


def test_report_with_only_warnings_can_be_approved(
    criteria: Criteria, complete_draft: Draft
) -> None:
    findings = [
        {"item_id": i.id, "passed": i.severity == "blocking", "details": ["Add strengths."]}
        for i in agent_items(criteria)
    ]
    fake = FakeAgentsOpenAI([answer(json.dumps({"findings": findings}))])
    hits = [
        SearchHit(chunk_id=c, case_id="case-002", doc_id="d", page=1, section="", text="t", score=1)
        for c in chunk_ids(complete_draft)
    ]
    report = review_draft(fake, criteria, complete_draft, hits, lambda q: [], START, ON_TIME)
    assert report.can_approve
    assert {r.item_id for r in report.warnings} == {"person_first_language", "strengths_included"}


def test_qa_input_marks_gap_statements(criteria: Criteria, complete_draft: Draft) -> None:
    complete_draft.sections[-1].claims.append(
        Claim(
            text="No prior services are documented.",
            elements=["information_gaps", "prior_services"],
        )
    )
    text = format_qa_input("case-002", agent_items(criteria), complete_draft)
    assert "- [gap statement] No prior services are documented." in text
