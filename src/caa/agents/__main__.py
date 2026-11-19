"""Publish the agents to Foundry, or draft one synthetic case end to end.

uv run python -m caa.agents publish
uv run python -m caa.agents draft case-002
"""

import argparse

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from caa.agents.definitions import publish_agents
from caa.agents.orchestrator import draft_assessment
from caa.config import get_settings
from caa.extraction.extractor import extract_facts
from caa.ingestion.embeddings import embed_texts
from caa.ingestion.pipeline import clients_from_settings
from caa.models import Draft
from caa.retrieval.search import SearchHit, list_case_chunks, search_case
from caa.rules import load_criteria
from caa.synthetic import load_case


def print_draft(draft: Draft) -> None:
    for section in draft.sections:
        print(f"\n## {section.title}")
        for claim in section.claims:
            cites = ", ".join(f"{c.doc_id} p{c.page}" for c in claim.citations) or "no citation"
            print(f"- {claim.text}  [{cites}] ({', '.join(claim.elements)})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m caa.agents")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("publish", help="create a new version of each agent in Foundry")
    draft_cmd = commands.add_parser("draft", help="extract and draft one synthetic case")
    draft_cmd.add_argument("case_id")
    args = parser.parse_args()

    settings = get_settings()
    settings.require("azure_foundry_project_endpoint")
    credential = DefaultAzureCredential()
    project = AIProjectClient(
        endpoint=settings.azure_foundry_project_endpoint, credential=credential
    )

    if args.command == "publish":
        for label in publish_agents(project, settings.chat_model_deployment):
            print(f"Published {label}")
        return

    clients = clients_from_settings(settings, credential)
    criteria = load_criteria()
    case = load_case(args.case_id)
    chunks = list_case_chunks(clients.search, case.case_id)

    def search(query: str) -> list[SearchHit]:
        [vector] = embed_texts(clients.openai, clients.embedding_deployment, [query])
        return search_case(clients.search, case.case_id, query, vector)

    facts = extract_facts(
        clients.openai,
        settings.chat_model_deployment,
        criteria,
        case.case_id,
        case.assessment_type,
        chunks,
    )
    print(f"Extracted {len(facts.facts)} facts")
    result = draft_assessment(
        project.get_openai_client(),
        criteria,
        case.case_id,
        case.assessment_type,
        facts,
        chunks,
        search,
    )
    print_draft(result.draft)
    if result.dropped_citations:
        print(f"\nDropped citations to unknown chunks: {result.dropped_citations}")


if __name__ == "__main__":
    main()
