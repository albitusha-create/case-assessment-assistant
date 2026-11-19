from typing import Any

import pytest

from caa.retrieval.index import EMBEDDING_DIMENSIONS, build_index
from caa.retrieval.search import case_filter, list_case_chunks, search_case


class FakeSearchClient:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    def search(self, search_text: str | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"search_text": search_text, **kwargs})
        return self.results


def test_case_filter() -> None:
    assert case_filter("case-001") == "case_id eq 'case-001'"


@pytest.mark.parametrize("bad", ["", "case-001' or case_id ne '", "case 1", "x" * 65])
def test_case_filter_rejects_unsafe_ids(bad: str) -> None:
    with pytest.raises(ValueError):
        case_filter(bad)


def test_search_case_always_filters_and_prefilters() -> None:
    client = FakeSearchClient([])
    search_case(client, "case-002", "living situation", [0.1, 0.2], top=3)
    [call] = client.calls
    assert call["filter"] == "case_id eq 'case-002'"
    assert call["vector_filter_mode"] == "preFilter"
    assert call["top"] == 3
    assert call["search_text"] == "living situation"


def test_search_case_maps_hits() -> None:
    row = {
        "chunk_id": "case-002_doc_p1_c0",
        "case_id": "case-002",
        "doc_id": "doc",
        "page": 1,
        "section": "Living situation",
        "text": "Lives with grandmother.",
        "@search.score": 0.03,
    }
    [hit] = search_case(FakeSearchClient([row]), "case-002", "q", [0.0])
    assert (hit.doc_id, hit.page, hit.score) == ("doc", 1, 0.03)


def test_index_schema_supports_case_scoping_and_vectors() -> None:
    fields = {f.name: f for f in build_index("case-chunks").fields}
    assert fields["chunk_id"].key
    assert fields["case_id"].filterable
    assert fields["embedding"].vector_search_dimensions == EMBEDDING_DIMENSIONS


def test_list_case_chunks_filters_and_sorts() -> None:
    def row(chunk_id: str, doc_id: str, page: int) -> dict[str, Any]:
        return {
            "chunk_id": chunk_id,
            "case_id": "case-001",
            "doc_id": doc_id,
            "page": page,
            "section": "",
            "text": "t",
            "@search.score": 1.0,
        }

    client = FakeSearchClient([row("b", "02", 1), row("a2", "01", 2), row("a1", "01", 1)])
    hits = list_case_chunks(client, "case-001")
    assert [h.chunk_id for h in hits] == ["a1", "a2", "b"]
    assert client.calls[0]["filter"] == "case_id eq 'case-001'"
