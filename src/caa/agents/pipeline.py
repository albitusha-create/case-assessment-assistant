"""Wire Azure clients to the workflow steps, for the CLI and the web app.

`run_case` is the whole automated part: extract, draft, QA. Everything after
it (review, approval) is a person's decision.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from caa.agents.orchestrator import DraftResult, draft_assessment, review_draft
from caa.config import Settings
from caa.extraction.extractor import extract_facts
from caa.extraction.schema import ExtractionResult
from caa.ingestion.embeddings import embed_texts
from caa.ingestion.pipeline import IngestionClients, clients_from_settings
from caa.qa.report import QAReport
from caa.retrieval.search import SearchHit, list_case_chunks, search_case
from caa.rules import Criteria, load_criteria
from caa.synthetic import SyntheticCase


@dataclass(frozen=True)
class Services:
    clients: IngestionClients
    project: AIProjectClient
    agents_openai: Any
    criteria: Criteria
    chat_deployment: str


@dataclass(frozen=True)
class CaseRun:
    facts: ExtractionResult
    drafted: DraftResult
    report: QAReport | None


def services_from_settings(settings: Settings) -> Services:
    settings.require("azure_foundry_project_endpoint")
    credential = DefaultAzureCredential()
    project = AIProjectClient(
        endpoint=settings.azure_foundry_project_endpoint, credential=credential
    )
    return Services(
        clients=clients_from_settings(settings, credential),
        project=project,
        agents_openai=project.get_openai_client(),
        criteria=load_criteria(),
        chat_deployment=settings.chat_model_deployment,
    )


def run_case(services: Services, case: SyntheticCase, today: date, with_qa: bool = True) -> CaseRun:
    clients = services.clients
    chunks = list_case_chunks(clients.search, case.case_id)

    def search(query: str) -> list[SearchHit]:
        [vector] = embed_texts(clients.openai, clients.embedding_deployment, [query])
        return search_case(clients.search, case.case_id, query, vector)

    facts = extract_facts(
        clients.openai,
        services.chat_deployment,
        services.criteria,
        case.case_id,
        case.assessment_type,
        chunks,
    )
    drafted = draft_assessment(
        services.agents_openai,
        services.criteria,
        case.case_id,
        case.assessment_type,
        facts,
        chunks,
        search,
    )
    report = None
    if with_qa:
        report = review_draft(
            services.agents_openai,
            services.criteria,
            drafted.draft,
            chunks,
            search,
            case.start_date,
            today,
        )
    return CaseRun(facts=facts, drafted=drafted, report=report)
