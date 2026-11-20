"""Publish the agents to Foundry, or run a synthetic case through the workflow.

uv run python -m caa.agents publish
uv run python -m caa.agents draft case-002     # extract and draft
uv run python -m caa.agents review case-002    # extract, draft and QA
"""

import argparse
from datetime import date

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from caa.agents.definitions import publish_agents
from caa.agents.orchestrator import draft_assessment, review_draft
from caa.config import get_settings
from caa.extraction.extractor import extract_facts
from caa.ingestion.embeddings import embed_texts
from caa.ingestion.pipeline import clients_from_settings
from caa.models import Draft
from caa.qa.report import QAReport
from caa.retrieval.search import SearchHit, list_case_chunks, search_case
from caa.rules import load_criteria
from caa.synthetic import load_case


def print_draft(draft: Draft) -> None:
    for section in draft.sections:
        print(f"\n## {section.title}")
        for claim in section.claims:
            cites = ", ".join(f"{c.doc_id} p{c.page}" for c in claim.citations) or "no citation"
            print(f"- {claim.text}  [{cites}] ({', '.join(claim.elements)})")


def print_report(report: QAReport) -> None:
    print(f"\n# QA report (checklist {report.checklist_version})")
    for result in report.results:
        status = "PASS" if result.passed else f"FAIL ({result.severity})"
        print(f"{status:<18} {result.item_id} [{result.checked_by}]")
        for finding in result.findings:
            print(f"    - {finding}")
    for gap in report.acknowledged_gaps:
        print(f"Known gap: {gap.element} ({gap.section_id})")
    verdict = "can be approved" if report.can_approve else "is BLOCKED"
    blocking, warnings = len(report.blocking_failures), len(report.warnings)
    print(f"\nDraft {verdict}: {blocking} blocking, {warnings} warnings")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m caa.agents")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("publish", help="create a new version of each agent in Foundry")
    for name in ("draft", "review"):
        command = commands.add_parser(name, help=f"{name} one synthetic case")
        command.add_argument("case_id")
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
    agents_openai = project.get_openai_client()
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
        agents_openai, criteria, case.case_id, case.assessment_type, facts, chunks, search
    )
    print_draft(result.draft)
    if result.dropped_citations:
        print(f"\nDropped citations to unknown chunks: {result.dropped_citations}")

    if args.command == "review":
        report = review_draft(
            agents_openai, criteria, result.draft, chunks, search, case.start_date, date.today()
        )
        print_report(report)


if __name__ == "__main__":
    main()
