from types import SimpleNamespace
from typing import Any

import pytest

from caa.extraction.extractor import (
    DRAFTED_ELEMENTS,
    check_facts,
    extract_facts,
    extractable_elements,
)
from caa.extraction.prompt import format_input
from caa.extraction.schema import Fact, ModelFact, ModelOutput
from caa.extraction.scoring import score_recall
from caa.models import Citation
from caa.retrieval.search import SearchHit
from caa.rules import Criteria
from caa.synthetic import ExpectedFact, list_case_ids, load_case


def chunk(chunk_id: str, doc_id: str = "01-intake-note", page: int = 1) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        case_id="case-001",
        doc_id=doc_id,
        page=page,
        section="",
        text="t",
        score=1.0,
    )


class FakeResponses:
    def __init__(self, output: ModelOutput | None) -> None:
        self.output = output
        self.kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.output)


def test_extractable_elements_skip_drafted_ones(criteria: Criteria) -> None:
    elements = extractable_elements(criteria, "initial_assessment")
    assert "living_situation" in elements
    assert not DRAFTED_ELEMENTS & set(elements)


def test_check_facts_takes_doc_and_page_from_the_index() -> None:
    output = ModelOutput(
        facts=[ModelFact(element="strengths", statement="Organized.", chunk_id="c2")]
    )
    result = check_facts("case-001", output, ["strengths"], [chunk("c2", "03-prior", page=2)])
    assert result.facts[0].citation == Citation(chunk_id="c2", doc_id="03-prior", page=2)
    assert result.rejected == []


def test_check_facts_rejects_unknown_elements_and_foreign_chunks() -> None:
    output = ModelOutput(
        facts=[
            ModelFact(element="risk_level", statement="High risk.", chunk_id="c1"),
            ModelFact(element="strengths", statement="Kind.", chunk_id="case-002_doc_p1_c0"),
        ]
    )
    result = check_facts("case-001", output, ["strengths"], [chunk("c1")])
    assert result.facts == []
    assert [r.reason for r in result.rejected] == ["unknown element", "chunk not in this case"]


def test_extract_facts_sends_chunks_and_schema(criteria: Criteria) -> None:
    output = ModelOutput(facts=[ModelFact(element="strengths", statement="Kind.", chunk_id="c1")])
    responses = FakeResponses(output)
    client = SimpleNamespace(responses=responses)

    result = extract_facts(
        client, "gpt-5.4-mini", criteria, "case-001", "initial_assessment", [chunk("c1")]
    )

    assert len(result.facts) == 1
    assert responses.kwargs["text_format"] is ModelOutput
    assert "chunk_id: c1" in responses.kwargs["input"]


def test_extract_facts_fails_loudly_without_parsed_output(criteria: Criteria) -> None:
    client = SimpleNamespace(responses=FakeResponses(None))
    with pytest.raises(RuntimeError):
        extract_facts(client, "m", criteria, "case-001", "initial_assessment", [chunk("c1")])


def test_format_input_lists_elements_and_page_labels() -> None:
    text = format_input("case-001", ["strengths"], [chunk("c1", page=2)])
    assert "- strengths" in text
    assert "### chunk_id: c1 (doc 01-intake-note, page 2)" in text


def _fact(element: str, doc_id: str, page: int) -> Fact:
    citation = Citation(chunk_id="x", doc_id=doc_id, page=page)
    return Fact(element=element, statement="s", citation=citation)


def test_score_recall_matches_element_doc_and_page() -> None:
    expected = [
        ExpectedFact(id="f1", element="strengths", statement="s", doc_id="d1", page=1),
        ExpectedFact(id="f2", element="living_situation", statement="s", doc_id="d2", page=1),
        ExpectedFact(id="f3", element="health_history", statement="s", doc_id="d1", page=2),
    ]
    facts = [
        _fact("strengths", "d1", 1),  # match
        _fact("living_situation", "d1", 1),  # wrong document
        _fact("health_history", "d1", 1),  # wrong page
    ]
    report = score_recall("case-001", expected, facts)
    assert report.found == ["f1"]
    assert [m.id for m in report.missed] == ["f2", "f3"]
    assert report.recall == pytest.approx(1 / 3)


def test_synthetic_cases_load() -> None:
    assert list_case_ids()[:2] == ["case-001", "case-002"]
    assert load_case("case-002").assessment_type == "initial_assessment"
