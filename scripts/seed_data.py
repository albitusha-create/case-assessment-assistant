"""Load the synthetic case PDFs into Blob Storage and the search index.

Usage (after `azd provision` and `azd env get-values > .env`):
    uv run python scripts/seed_data.py              # all cases
    uv run python scripts/seed_data.py case-002     # one case

Safe to re-run: blobs are overwritten and chunk ids are deterministic.
"""

import sys
from pathlib import Path

from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient

from caa.config import get_settings
from caa.ingestion.embeddings import embed_texts
from caa.ingestion.pipeline import clients_from_settings, ingest_pdf
from caa.retrieval.index import ensure_index
from caa.retrieval.search import search_case

CASES_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "cases"
SMOKE_QUERY = "living situation and who the person lives with"


def main(case_ids: list[str]) -> None:
    settings = get_settings()
    credential = DefaultAzureCredential()
    clients = clients_from_settings(settings, credential)

    ensure_index(
        SearchIndexClient(settings.azure_search_endpoint, credential),
        settings.azure_search_index,
    )
    print(f"Index ready: {settings.azure_search_index}")

    case_dirs = sorted(d for d in CASES_DIR.iterdir() if d.is_dir())
    if case_ids:
        case_dirs = [d for d in case_dirs if d.name in case_ids]

    for case_dir in case_dirs:
        for pdf in sorted(case_dir.glob("*.pdf")):
            chunks = ingest_pdf(clients, case_dir.name, pdf.stem, pdf.read_bytes())
            pages = sorted({c.page for c in chunks})
            print(f"{case_dir.name}/{pdf.stem}: {len(chunks)} chunks from pages {pages}")

    # Smoke test: one scoped query per case. Every hit must belong to that case.
    # (New documents can take a second or two to become searchable.)
    [vector] = embed_texts(clients.openai, clients.embedding_deployment, [SMOKE_QUERY])
    for case_dir in case_dirs:
        hits = search_case(clients.search, case_dir.name, SMOKE_QUERY, vector, top=3)
        print(f"\n{case_dir.name}: top hits for '{SMOKE_QUERY}'")
        for hit in hits:
            if hit.case_id != case_dir.name:
                raise SystemExit(f"Case filter leaked {hit.chunk_id} into {case_dir.name}")
            print(f"  {hit.doc_id} p{hit.page} [{hit.section}] {hit.text[:70]!r}")


if __name__ == "__main__":
    main(sys.argv[1:])
