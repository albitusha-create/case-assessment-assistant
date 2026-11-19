"""Extract cited facts for one case: one LLM call, then deterministic checks.

The model proposes facts. Our code decides which ones are kept: a fact must use
known elements and cite a chunk that really belongs to this case. Document id
and page come from the index, never from the model.
"""

from collections.abc import Collection
from typing import Any, Protocol

from caa.extraction.prompt import INSTRUCTIONS, format_input
from caa.extraction.schema import ExtractionResult, Fact, ModelOutput, RejectedFact
from caa.models import Citation
from caa.retrieval.search import SearchHit
from caa.rules import Criteria, get_required_sections

# Written by the drafting agent from the facts, not extracted from documents.
DRAFTED_ELEMENTS = {"summary", "information_gaps", "considerations_for_staff"}


class SupportsResponses(Protocol):
    """The slice of the OpenAI client we use. Lets tests pass a fake."""

    @property
    def responses(self) -> Any: ...


def extractable_elements(criteria: Criteria, assessment_type: str) -> dict[str, str]:
    """Element name to definition, in section order, without the drafted ones."""
    elements: dict[str, str] = {}
    for section in get_required_sections(criteria, assessment_type):
        for name in section.required_elements:
            if name not in DRAFTED_ELEMENTS:
                elements[name] = criteria.element_definitions.get(name, "")
    return elements


def ask_model(
    client: SupportsResponses,
    deployment: str,
    case_id: str,
    elements: dict[str, str],
    chunks: list[SearchHit],
) -> ModelOutput:
    response = client.responses.parse(
        model=deployment,
        instructions=INSTRUCTIONS,
        input=format_input(case_id, elements, chunks),
        text_format=ModelOutput,
    )
    parsed = response.output_parsed
    if not isinstance(parsed, ModelOutput):
        raise RuntimeError("Model returned no parseable output")
    return parsed


def check_facts(
    case_id: str, output: ModelOutput, elements: Collection[str], chunks: list[SearchHit]
) -> ExtractionResult:
    """Keep a fact only if it cites a chunk of this case and has a known label.

    Unknown labels are dropped from a fact; a fact left with no known label is
    rejected.
    """
    by_id = {c.chunk_id: c for c in chunks}
    facts: list[Fact] = []
    rejected: list[RejectedFact] = []
    for proposed in output.facts:
        chunk = by_id.get(proposed.chunk_id)
        known = [e for e in dict.fromkeys(proposed.elements) if e in elements]
        if not known:
            rejected.append(RejectedFact(fact=proposed, reason="unknown element"))
        elif chunk is None:
            rejected.append(RejectedFact(fact=proposed, reason="chunk not in this case"))
        else:
            citation = Citation(chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page=chunk.page)
            facts.append(Fact(elements=known, statement=proposed.statement, citation=citation))
    return ExtractionResult(case_id=case_id, facts=facts, rejected=rejected)


def extract_facts(
    client: SupportsResponses,
    deployment: str,
    criteria: Criteria,
    case_id: str,
    assessment_type: str,
    chunks: list[SearchHit],
) -> ExtractionResult:
    elements = extractable_elements(criteria, assessment_type)
    output = ask_model(client, deployment, case_id, elements, chunks)
    return check_facts(case_id, output, elements, chunks)
