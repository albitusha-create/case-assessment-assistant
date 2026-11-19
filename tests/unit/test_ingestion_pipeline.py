from types import SimpleNamespace
from typing import Any, cast

import pytest

from caa.ingestion import pipeline
from caa.ingestion.chunking import Chunk
from caa.ingestion.embeddings import embed_texts
from caa.ingestion.layout import Paragraph


class FakeEmbeddings:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def create(self, model: str, input: list[str]) -> SimpleNamespace:
        self.batches.append(input)
        # Return items out of order to prove we sort by index.
        data = [SimpleNamespace(index=i, embedding=[float(len(t))]) for i, t in enumerate(input)]
        return SimpleNamespace(data=list(reversed(data)))


def test_embed_texts_batches_and_keeps_order() -> None:
    fake = FakeEmbeddings()
    client = cast(Any, SimpleNamespace(embeddings=fake))
    texts = ["a" * n for n in range(1, 21)]
    vectors = embed_texts(client, "text-embedding-3-small", texts)
    assert vectors == [[float(n)] for n in range(1, 21)]
    assert [len(b) for b in fake.batches] == [16, 4]


def test_to_search_documents_requires_one_vector_per_chunk() -> None:
    chunk = Chunk(chunk_id="c", case_id="case-001", doc_id="d", page=1, section="", text="t")
    assert pipeline.to_search_documents([chunk], [[0.5]])[0]["embedding"] == [0.5]
    with pytest.raises(ValueError):
        pipeline.to_search_documents([chunk], [])


def test_ingest_pdf_runs_each_step(monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded: dict[str, Any] = {}
    indexed: list[dict[str, object]] = []
    monkeypatch.setattr(
        pipeline, "analyze_layout", lambda client, data: [Paragraph(1, "Lives alone.", False)]
    )
    monkeypatch.setattr(pipeline, "embed_texts", lambda client, dep, texts: [[1.0] for _ in texts])
    clients = pipeline.IngestionClients(
        blobs=cast(
            Any,
            SimpleNamespace(upload_blob=lambda name, data, overwrite: uploaded.update(name=name)),
        ),
        docintel=cast(Any, None),
        openai=cast(Any, None),
        search=cast(Any, SimpleNamespace(merge_or_upload_documents=indexed.extend)),
        embedding_deployment="text-embedding-3-small",
    )

    chunks = pipeline.ingest_pdf(clients, "case-001", "01-intake-note", b"%PDF")

    assert uploaded["name"] == "case-001/01-intake-note.pdf"
    assert [c.chunk_id for c in chunks] == ["case-001_01-intake-note_p1_c0"]
    assert indexed[0]["case_id"] == "case-001"
