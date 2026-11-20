"""Run the function tools an agent asks for (ADR 0004: rules as tools).

The orchestrator builds the handlers with the case already bound, so every
search is filtered to that case and every rule answers for its assessment type.
"""

import json
from collections.abc import Callable
from typing import Any

from caa.retrieval.search import SearchHit
from caa.rules import Criteria, get_required_sections

ToolHandler = Callable[[dict[str, Any]], Any]


def make_drafting_tools(
    criteria: Criteria,
    assessment_type: str,
    search: Callable[[str], list[SearchHit]],
) -> dict[str, ToolHandler]:
    def required_sections(_: dict[str, Any]) -> Any:
        return [
            {
                "id": s.id,
                "title": s.title,
                "required_elements": {
                    e: criteria.element_definitions.get(e, "") for e in s.required_elements
                },
            }
            for s in get_required_sections(criteria, assessment_type)
        ]

    def search_documents(args: dict[str, Any]) -> Any:
        return [
            hit.model_dump(include={"chunk_id", "doc_id", "page", "text"})
            for hit in search(str(args["query"]))
        ]

    return {"get_required_sections": required_sections, "search_case_documents": search_documents}


def dispatch(handlers: dict[str, ToolHandler], name: str, arguments: str) -> str:
    """Run one tool call and return its output as JSON text for the agent.

    Errors go back to the agent as data instead of crashing the run, so it can
    recover (for example after calling a tool that does not exist).
    """
    handler = handlers.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return json.dumps(handler(json.loads(arguments or "{}")))
    except (ValueError, KeyError, TypeError) as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
