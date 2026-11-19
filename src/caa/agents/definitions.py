"""Foundry prompt agent definitions (ADR 0002).

The agent lives in Foundry: versioned, traced and visible in the portal. Its
tools are function tools, so Foundry only describes them to the model. Our
code runs them (see tool_dispatch.py) with the case id already bound.
"""

from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    FunctionTool,
    PromptAgentDefinition,
    PromptAgentDefinitionTextOptions,
    TextResponseFormatJsonSchema,
)

from caa.agents.schema import draft_json_schema

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DRAFTING_AGENT = "caa-drafting"

# Note there is no case_id parameter: the model cannot choose which case to read.
GET_REQUIRED_SECTIONS = FunctionTool(
    name="get_required_sections",
    description="Required sections, their required elements and element definitions "
    "for this case's assessment type.",
    parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    strict=True,
)
SEARCH_CASE_DOCUMENTS = FunctionTool(
    name="search_case_documents",
    description="Hybrid search over this case's documents. Returns chunk ids, "
    "document, page and text.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to look for."}},
        "required": ["query"],
        "additionalProperties": False,
    },
    strict=True,
)


def drafting_definition(model_deployment: str) -> PromptAgentDefinition:
    return PromptAgentDefinition(
        model=model_deployment,
        instructions=(PROMPTS_DIR / "drafting.md").read_text(),
        tools=[GET_REQUIRED_SECTIONS, SEARCH_CASE_DOCUMENTS],
        text=PromptAgentDefinitionTextOptions(
            format=TextResponseFormatJsonSchema(
                name="assessment_draft", schema=draft_json_schema(), strict=True
            )
        ),
    )


def publish_agents(project: AIProjectClient, model_deployment: str) -> list[str]:
    """Create a new version of each agent. Returns "name:version" labels."""
    version = project.agents.create_version(
        agent_name=DRAFTING_AGENT,
        definition=drafting_definition(model_deployment),
        description="Drafts a cited case assessment from extracted facts.",
    )
    return [f"{version.name}:{version.version}"]
