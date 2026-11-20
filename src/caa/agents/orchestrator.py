"""The assessment workflow in plain code (ADR 0002).

Hour 4 covers the first two steps: extract facts, then draft. QA, review and
the audit log are added as their own steps later.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from caa.agents.definitions import DRAFTING_AGENT
from caa.agents.runner import run_agent
from caa.agents.schema import DraftOutput
from caa.agents.tool_dispatch import dispatch, make_drafting_tools
from caa.extraction.schema import ExtractionResult
from caa.models import Citation, Claim, Draft, DraftSection
from caa.retrieval.search import SearchHit
from caa.rules import Criteria


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
