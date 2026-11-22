"""Check one section of the agency form while the worker writes it.

The worker types in the agency portal and asks for a check. Two kinds of
results come back, the same split as the supervisor's QA report:

- Rule checks run in code: wording that reads as a determination.
- Judgment items from the QA checklist go to the model, scoped to this section,
  together with facts from the case documents the worker could add.

Everything here is advice. Nothing blocks the worker's save or submit; the
portal owns that. As in extraction, the model cites chunk ids only and code
looks up the document and page, dropping any chunk that is not in this case.
"""

from collections.abc import Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from caa.assist.prompt import INSTRUCTIONS, format_input
from caa.integrations.form_mapping import ELEMENT_TO_DOMAINS
from caa.portal.form import Domain
from caa.retrieval.search import SearchHit
from caa.rules import Criteria
from caa.rules.criteria import ChecklistItem
from caa.rules.language import find_prohibited_phrases

MAX_TEXT = 6000

# Checklist items the model judges for one section, worded for a section rather
# than a whole draft. Severity still comes from the checklist.
SECTION_WORDING = {
    "claims_supported": "Each statement agrees with the case documents.",
    "conflicts_named": "Where documents disagree, both versions are named.",
    "safety_concerns_carried": "Safety concerns in the documents for this section are mentioned.",
    "person_first_language": "Language is person first and non-stigmatizing.",
    "strengths_included": "Strengths are described specifically.",
}
ONLY_FOR = {"strengths_included": "strengths"}
NOT_REPORTED = "The assistant did not report on this item. Check it yourself."


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelDetail(_Strict):
    text: str
    chunk_ids: list[str]


class ModelItem(_Strict):
    item_id: str
    passed: bool
    details: list[ModelDetail]


class ModelSuggestion(_Strict):
    text: str
    chunk_id: str


class ModelOutput(_Strict):
    items: list[ModelItem]
    suggestions: list[ModelSuggestion]


class Source(BaseModel):
    doc_id: str
    page: int


class Finding(BaseModel):
    text: str
    sources: list[Source]


class ItemResult(BaseModel):
    item_id: str
    description: str
    checked_by: Literal["rule", "agent"]
    severity: Literal["blocking", "warning"]
    passed: bool
    findings: list[Finding]


class Suggestion(BaseModel):
    text: str
    source: Source


class SectionCheck(BaseModel):
    case_id: str
    domain_id: str
    results: list[ItemResult]
    suggestions: list[Suggestion]
    # Chunk ids the model cited that are not in this case: removed, and counted.
    dropped_citations: int = 0

    @property
    def open_items(self) -> list[str]:
        return [r.item_id for r in self.results if not r.passed]


# (case_id, domain, worker's text) -> result. The app passes in the real one.
SectionChecker = Callable[[str, Domain, str], SectionCheck]


class SupportsResponses(Protocol):
    @property
    def responses(self) -> Any: ...


def assist_allowed(domain: Domain) -> bool:
    """The same line the portal draws for pre-fill: no clinical sections and no
    self-rating in the person's own words."""
    return domain.filled_by == "worker" and domain.assistant_may_prefill


def domain_elements(criteria: Criteria, domain_id: str) -> dict[str, str]:
    """Our criteria elements that map to this form section, with definitions."""
    return {
        element: criteria.element_definitions.get(element, "")
        for element, domains in ELEMENT_TO_DOMAINS.items()
        if domain_id in domains
    }


def judged_items(criteria: Criteria, domain_id: str) -> list[ChecklistItem]:
    return [
        item
        for item in criteria.checklist.items
        if item.id in SECTION_WORDING and ONLY_FOR.get(item.id, domain_id) == domain_id
    ]


def rule_results(criteria: Criteria, text: str) -> list[ItemResult]:
    item = next(i for i in criteria.checklist.items if i.id == "no_determinations")
    phrases = find_prohibited_phrases(text, criteria.checklist.prohibited_phrases)
    findings = [
        Finding(
            text=f'"{p}" reads as a determination. Describe what was observed or reported '
            "instead; decisions are made outside this form.",
            sources=[],
        )
        for p in phrases
    ]
    return [
        ItemResult(
            item_id=item.id,
            description="No eligibility, risk, diagnosis or level of care determinations.",
            checked_by="rule",
            severity=item.severity,
            passed=not findings,
            findings=findings,
        )
    ]


def ask_model(
    client: SupportsResponses,
    deployment: str,
    user_input: str,
) -> ModelOutput:
    response = client.responses.parse(
        model=deployment, instructions=INSTRUCTIONS, input=user_input, text_format=ModelOutput
    )
    parsed = response.output_parsed
    if not isinstance(parsed, ModelOutput):
        raise RuntimeError("Model returned no parseable output")
    return parsed


def to_results(
    items: list[ChecklistItem], output: ModelOutput, chunks: list[SearchHit]
) -> tuple[list[ItemResult], list[Suggestion], int]:
    """Resolve chunk ids to pages, fail closed on unreported items, drop foreign chunks."""
    by_id = {c.chunk_id: c for c in chunks}
    dropped = 0

    def sources(chunk_ids: list[str]) -> list[Source]:
        nonlocal dropped
        found: list[Source] = []
        for chunk_id in dict.fromkeys(chunk_ids):
            chunk = by_id.get(chunk_id)
            if chunk is None:
                dropped += 1
            else:
                found.append(Source(doc_id=chunk.doc_id, page=chunk.page))
        return found

    reported = {i.item_id: i for i in output.items}
    results: list[ItemResult] = []
    for item in items:
        got = reported.get(item.id)
        passed = got is not None and got.passed
        if got is None:
            findings = [Finding(text=NOT_REPORTED, sources=[])]
        elif passed:
            findings = []
        else:
            findings = [Finding(text=d.text, sources=sources(d.chunk_ids)) for d in got.details]
        results.append(
            ItemResult(
                item_id=item.id,
                description=SECTION_WORDING[item.id],
                checked_by="agent",
                severity=item.severity,
                passed=passed,
                findings=findings,
            )
        )

    suggestions: list[Suggestion] = []
    for s in output.suggestions[:5]:
        found = sources([s.chunk_id])
        if found:  # a suggestion with no source in this case is not shown
            suggestions.append(Suggestion(text=s.text.strip(), source=found[0]))
    return results, suggestions, dropped


def check_section(
    client: SupportsResponses,
    deployment: str,
    criteria: Criteria,
    case_id: str,
    domain: Domain,
    text: str,
    chunks: list[SearchHit],
) -> SectionCheck:
    if not assist_allowed(domain):
        raise ValueError(f"The assistant does not review the {domain.title} section")
    text = text[:MAX_TEXT]
    items = judged_items(criteria, domain.id)
    user_input = format_input(
        domain,
        domain_elements(criteria, domain.id),
        [(item, SECTION_WORDING[item.id]) for item in items],
        text,
        chunks,
    )
    judged, suggestions, dropped = to_results(
        items, ask_model(client, deployment, user_input), chunks
    )
    order = {item.id: index for index, item in enumerate(criteria.checklist.items)}
    results = sorted(rule_results(criteria, text) + judged, key=lambda r: order[r.item_id])
    return SectionCheck(
        case_id=case_id,
        domain_id=domain.id,
        results=results,
        suggestions=suggestions,
        dropped_citations=dropped,
    )
