"""Runs against the real index after `scripts/seed_data.py`.

uv run pytest -m integration
"""

import pytest
from azure.identity import DefaultAzureCredential

from caa.config import get_settings
from caa.ingestion.embeddings import embed_texts
from caa.ingestion.pipeline import clients_from_settings
from caa.retrieval.search import search_case

pytestmark = pytest.mark.integration
CASES = ["case-001", "case-002", "case-003", "case-004"]


@pytest.mark.parametrize("case_id", CASES)
def test_every_hit_belongs_to_the_queried_case(case_id: str) -> None:
    clients = clients_from_settings(get_settings(), DefaultAzureCredential())
    query = "housing, school, health and family history"
    [vector] = embed_texts(clients.openai, clients.embedding_deployment, [query])

    hits = search_case(clients.search, case_id, query, vector, top=10)

    assert hits, f"no chunks indexed for {case_id}; run scripts/seed_data.py"
    assert {h.case_id for h in hits} == {case_id}
