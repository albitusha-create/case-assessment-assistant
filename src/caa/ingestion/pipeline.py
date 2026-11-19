"""Ingest one PDF: store it, read its layout, chunk, embed and index.

Each step is a small function in its own module. This file only wires them in
order, so the whole flow reads top to bottom.
"""

from dataclasses import dataclass

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import TokenCredential
from azure.search.documents import SearchClient
from azure.storage.blob import BlobServiceClient, ContainerClient
from openai import OpenAI

from caa.config import Settings
from caa.ingestion.chunking import Chunk, chunk_paragraphs
from caa.ingestion.embeddings import embed_texts, make_openai_client
from caa.ingestion.layout import analyze_layout


@dataclass(frozen=True)
class IngestionClients:
    blobs: ContainerClient
    docintel: DocumentIntelligenceClient
    openai: OpenAI
    search: SearchClient
    embedding_deployment: str


def blob_name(case_id: str, doc_id: str) -> str:
    return f"{case_id}/{doc_id}.pdf"


def to_search_documents(chunks: list[Chunk], vectors: list[list[float]]) -> list[dict[str, object]]:
    if len(chunks) != len(vectors):
        raise ValueError("Need exactly one vector per chunk")
    return [
        {**chunk.model_dump(), "embedding": vector}
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def ingest_pdf(
    clients: IngestionClients, case_id: str, doc_id: str, pdf_bytes: bytes
) -> list[Chunk]:
    # 1. Keep the original document. The blob path groups files by case.
    clients.blobs.upload_blob(blob_name(case_id, doc_id), pdf_bytes, overwrite=True)

    # 2. Paragraphs with page numbers, then page-bounded chunks.
    paragraphs = analyze_layout(clients.docintel, pdf_bytes)
    chunks = chunk_paragraphs(case_id, doc_id, paragraphs)
    if not chunks:
        return []

    # 3. Embed in our code (not an indexer), so each step is visible and testable.
    vectors = embed_texts(clients.openai, clients.embedding_deployment, [c.text for c in chunks])

    # 4. Upsert. Chunk ids are deterministic, so re-running overwrites old chunks.
    clients.search.merge_or_upload_documents(to_search_documents(chunks, vectors))
    return chunks


def clients_from_settings(settings: Settings, credential: TokenCredential) -> IngestionClients:
    """Build every client from endpoints only. The credential does all auth."""
    settings.require(
        "azure_storage_account_url",
        "azure_docintel_endpoint",
        "azure_openai_endpoint",
        "azure_search_endpoint",
    )
    return IngestionClients(
        blobs=BlobServiceClient(
            settings.azure_storage_account_url, credential
        ).get_container_client(settings.azure_storage_container),
        docintel=DocumentIntelligenceClient(settings.azure_docintel_endpoint, credential),
        openai=make_openai_client(settings.azure_openai_endpoint, credential),
        search=SearchClient(
            settings.azure_search_endpoint, settings.azure_search_index, credential
        ),
        embedding_deployment=settings.embedding_model_deployment,
    )
