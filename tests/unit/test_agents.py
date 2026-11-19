import json
from types import SimpleNamespace
from typing import Any

import pytest

from caa.agents.definitions import DRAFTING_AGENT, drafting_definition
from caa.agents.orchestrator import draft_assessment, format_drafting_input, to_draft
from caa.agents.runner import MAX_TURNS, run_agent
from caa.agents.schema import DraftOutput, ModelClaim, ModelSection
from caa.agents.tool_dispatch import dispatch, make_drafting_tools
from caa.extraction.schema import ExtractionResult, Fact
from caa.models import Citation
from caa.retrieval.search import SearchHit
from caa.rules import Criteria


def hit(chunk_id: str, doc_id: str = "01-intake-note", page: int = 1) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        case_id="case-002",
        doc_id=doc_id,
        page=page,
        section="",
        text="t",
        score=1.0,
    )


def call(name: str, arguments: str, call_id: str = "call-1") -> SimpleNamespace:
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, call_id=call_id)


class FakeAgentsOpenAI:
    """Plays back scripted responses and records every request."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.scripted = responses
        self.requests: list[dict[str, Any]] = []
        self.responses = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        return self.scripted.pop(0)


def answer(text: str, response_id: str = "resp-2") -> SimpleNamespace:
    return SimpleNamespace(id=response_id, output=[], output_text=text)


# Tool dispatch


def test_required_sections_tool_returns_sections_with_definitions(criteria: Criteria) -> None:
    tools = make_drafting_tools(criteria, "initial_assessment", search=lambda q: [])
    sections = json.loads(dispatch(tools, "get_required_sections", "{}"))
    assert sections[0]["id"] == "presenting_concerns"
    assert sections[0]["required_elements"]["referral_source"]


def test_search_tool_uses_the_bound_search(criteria: Criteria) -> None:
    queries: list[str] = []

    def search(query: str) -> list[SearchHit]:
        queries.append(query)
        return [hit("c1", page=2)]

    tools = make_drafting_tools(criteria, "initial_assessment", search)
    result = json.loads(dispatch(tools, "search_case_documents", '{"query": "housing"}'))
    assert queries == ["housing"]
    assert result == [{"chunk_id": "c1", "doc_id": "01-intake-note", "page": 2, "text": "t"}]


def test_dispatch_returns_errors_as_data(criteria: Criteria) -> None:
    tools = make_drafting_tools(criteria, "initial_assessment", search=lambda q: [])
    assert "Unknown tool" in json.loads(dispatch(tools, "delete_case", "{}"))["error"]
    assert "KeyError" in json.loads(dispatch(tools, "search_case_documents", "{}"))["error"]


# Agent definition


def test_drafting_definition_has_tools_without_case_id_and_strict_output() -> None:
    definition = drafting_definition("gpt-5.4-mini")
    names = [tool.name for tool in definition.tools]
    assert names == ["get_required_sections", "search_case_documents"]
    for tool in definition.tools:
        assert "case_id" not in tool.parameters["properties"]
    assert definition.text.format.strict is True
    assert "eligibility" in definition.instructions


# Runner


def test_run_agent_runs_tools_and_continues_the_chain() -> None:
    fake = FakeAgentsOpenAI(
        [
            SimpleNamespace(id="resp-1", output=[call("get_required_sections", "{}")]),
            answer('{"sections": []}'),
        ]
    )
    ran: list[str] = []

    def run_tool(name: str, arguments: str) -> str:
        ran.append(name)
        return "[]"

    text = run_agent(fake, DRAFTING_AGENT, "draft case-002", run_tool)

    assert text == '{"sections": []}'
    assert ran == ["get_required_sections"]
    second = fake.requests[1]
    assert second["previous_response_id"] == "resp-1"
    assert second["input"] == [
        {"type": "function_call_output", "call_id": "call-1", "output": "[]"}
    ]
    assert second["extra_body"]["agent_reference"]["name"] == DRAFTING_AGENT


def test_run_agent_stops_after_max_turns() -> None:
    looping = [SimpleNamespace(id=f"r{i}", output=[call("x", "{}")]) for i in range(MAX_TURNS + 1)]
    with pytest.raises(RuntimeError):
        run_agent(FakeAgentsOpenAI(looping), DRAFTING_AGENT, "go", lambda n, a: "{}")


# Orchestrator


def test_to_draft_resolves_pages_and_drops_unknown_chunks() -> None:
    output = DraftOutput(
        sections=[
            ModelSection(
                id="current_functioning",
                title="Current functioning and strengths",
                claims=[
                    ModelClaim(
                        text="Lives with grandmother.",
                        elements=["living_situation"],
                        chunk_ids=["c1", "case-001_made_up"],
                    )
                ],
            )
        ]
    )
    result = to_draft("case-002", "initial_assessment", output, [hit("c1", page=2)])
    claim = result.draft.sections[0].claims[0]
    assert claim.citations == [Citation(chunk_id="c1", doc_id="01-intake-note", page=2)]
    assert result.dropped_citations == ["case-001_made_up"]


def facts() -> ExtractionResult:
    citation = Citation(chunk_id="c1", doc_id="01-intake-note", page=1)
    fact = Fact(
        elements=["living_situation"], statement="Lives with grandmother.", citation=citation
    )
    return ExtractionResult(case_id="case-002", facts=[fact], rejected=[])


def test_format_drafting_input_lists_facts_with_chunk_ids() -> None:
    text = format_drafting_input("case-002", "initial_assessment", facts())
    assert "- [c1] (living_situation) Lives with grandmother." in text


def test_draft_assessment_end_to_end_with_a_fake_agent(criteria: Criteria) -> None:
    draft_json = json.dumps(
        {
            "sections": [
                {
                    "id": "current_functioning",
                    "title": "Current functioning and strengths",
                    "claims": [
                        {
                            "text": "Lives with grandmother.",
                            "elements": ["living_situation"],
                            "chunk_ids": ["c1"],
                        }
                    ],
                }
            ]
        }
    )
    fake = FakeAgentsOpenAI([answer(draft_json)])
    result = draft_assessment(
        fake, criteria, "case-002", "initial_assessment", facts(), [hit("c1")], search=lambda q: []
    )
    assert result.draft.sections[0].claims[0].citations[0].page == 1
    assert "Lives with grandmother." in fake.requests[0]["input"]
