"""The assessment workflow in plain code (ADR 0002).

Steps so far: extract facts, draft, then QA (rule checks in code plus the QA
agent). Human review and the audit log are added as their own steps later.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any

from caa.agents.definitions import DRAFTING_AGENT, QA_AGENT
from caa.agents.runner import run_agent
from caa.agents.schema import DraftOutput, QAOutput
from caa.agents.tool_dispatch import dispatch, make_drafting_tools, make_qa_tools
from caa.extraction.schema import ExtractionResult
from caa.models import Citation, Claim, Draft, DraftSection
from caa.qa.report import CheckResult, QAReport
from caa.qa.rule_checks import run_rule_checks
from caa.retrieval.search import SearchHit
from caa.rules import Criteria
from caa.rules.criteria import ChecklistItem


@dataclass(frozen=True)
class DraftResult:
    draft: Draft
    # Chunk ids the agent cited that are not in this case. Removed from the
    # draft, so the citation coverage rule flags the claims that relied on them.
    dropped_citations: list[str]


def format_drafting_input(case_id: str, assessment_type: str, facts: ExtractionResult) -> str:
    lines = [f"Case: {case_id}", f"Assessment type: {assessment_type}", "", "Facts:"]
    for fact in facts.facts:
        lines.append(f"- [{fact.citation.chunk_id}] ({', '.join(fact.elements)}) {fact.statement}")
    return "\n".join(lines)


def to_draft(
    case_id: str, assessment_type: str, output: DraftOutput, chunks: list[SearchHit]
) -> DraftResult:
    """Turn the agent's JSON into our Draft model, resolving chunk ids to pages."""
    by_id = {c.chunk_id: c for c in chunks}
    dropped: list[str] = []
    sections: list[DraftSection] = []
    for model_section in output.sections:
        claims: list[Claim] = []
        for model_claim in model_section.claims:
            citations: list[Citation] = []
            for chunk_id in model_claim.chunk_ids:
                chunk = by_id.get(chunk_id)
                if chunk is None:
                    dropped.append(chunk_id)
                else:
                    citations.append(
                        Citation(chunk_id=chunk_id, doc_id=chunk.doc_id, page=chunk.page)
                    )
            claims.append(
                Claim(text=model_claim.text, citations=citations, elements=model_claim.elements)
            )
        sections.append(DraftSection(id=model_section.id, title=model_section.title, claims=claims))
    draft = Draft(case_id=case_id, assessment_type=assessment_type, sections=sections)
    return DraftResult(draft=draft, dropped_citations=dropped)


def draft_assessment(
    agents_openai: Any,
    criteria: Criteria,
    case_id: str,
    assessment_type: str,
    facts: ExtractionResult,
    chunks: list[SearchHit],
    search: Callable[[str], list[SearchHit]],
) -> DraftResult:
    """Run the Drafting agent on extracted facts. `search` is already scoped to the case."""
    handlers = make_drafting_tools(criteria, assessment_type, search)
    text = run_agent(
        agents_openai,
        DRAFTING_AGENT,
        format_drafting_input(case_id, assessment_type, facts),
        partial(dispatch, handlers),
    )
    output = DraftOutput.model_validate_json(text)
    return to_draft(case_id, assessment_type, output, chunks)


def format_qa_input(case_id: str, items: list[ChecklistItem], draft: Draft) -> str:
    lines = [f"Case: {case_id}", "", "Checklist items to check:"]
    lines += [f"- {item.id}: {item.description}" for item in items]
    lines += ["", "Draft:"]
    for section in draft.sections:
        lines += ["", f"## {section.title} ({section.id})"]
        for claim in section.claims:
            cites = ", ".join(c.chunk_id for c in claim.citations) or "none"
            lines.append(f"- {claim.text} [elements: {', '.join(claim.elements)}; chunks: {cites}]")
    return "\n".join(lines)


def agent_results(items: list[ChecklistItem], output: QAOutput) -> list[CheckResult]:
    """One result per agent item, in checklist order.

    Severity comes from the checklist, never from the model. An item the agent
    did not report fails (fail closed), so a skipped check cannot pass silently.
    """
    by_id = {finding.item_id: finding for finding in output.findings}
    results: list[CheckResult] = []
    for item in items:
        finding = by_id.get(item.id)
        passed = finding is not None and finding.passed
        if finding is None:
            details = ["The QA agent did not report on this item."]
        else:
            details = finding.details
        results.append(
            CheckResult(
                item_id=item.id,
                description=item.description,
                checked_by=item.checked_by,
                severity=item.severity,
                passed=passed,
                findings=[] if passed else details,
            )
        )
    return results


def review_draft(
    agents_openai: Any,
    criteria: Criteria,
    draft: Draft,
    chunks: list[SearchHit],
    search: Callable[[str], list[SearchHit]],
    start_date: date,
    today: date,
) -> QAReport:
    """Rule items run in code; judgment items go to the QA agent. One report."""
    rule_results, completeness = run_rule_checks(
        criteria, draft, {c.chunk_id for c in chunks}, start_date, today
    )

    agent_items = [i for i in criteria.checklist.items if i.checked_by == "agent"]
    text = run_agent(
        agents_openai,
        QA_AGENT,
        format_qa_input(draft.case_id, agent_items, draft),
        partial(dispatch, make_qa_tools(chunks, search)),
    )
    judged = agent_results(agent_items, QAOutput.model_validate_json(text))

    order = {item.id: index for index, item in enumerate(criteria.checklist.items)}
    results = sorted(rule_results + judged, key=lambda r: order[r.item_id])
    return QAReport(
        case_id=draft.case_id,
        checklist_version=criteria.checklist.version,
        results=results,
        acknowledged_gaps=completeness.acknowledged_gaps,
    )
