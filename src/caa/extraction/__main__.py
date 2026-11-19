"""Extract and print the cited facts for one synthetic case.

uv run python -m caa.extraction case-001
"""

import sys

from azure.identity import DefaultAzureCredential

from caa.config import get_settings
from caa.extraction.extractor import extract_facts
from caa.ingestion.pipeline import clients_from_settings
from caa.retrieval.search import list_case_chunks
from caa.rules import load_criteria
from caa.synthetic import load_case


def main(case_id: str) -> None:
    settings = get_settings()
    clients = clients_from_settings(settings, DefaultAzureCredential())
    case = load_case(case_id)
    chunks = list_case_chunks(clients.search, case_id)

    result = extract_facts(
        clients.openai,
        settings.chat_model_deployment,
        load_criteria(),
        case_id,
        case.assessment_type,
        chunks,
    )

    for fact in sorted(result.facts, key=lambda f: f.element):
        c = fact.citation
        print(f"{fact.element:<26} {fact.statement}  [{c.doc_id} p{c.page}]")
    for bad in result.rejected:
        print(f"REJECTED ({bad.reason}): {bad.fact.statement}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m caa.extraction <case-id>")
    main(sys.argv[1])
