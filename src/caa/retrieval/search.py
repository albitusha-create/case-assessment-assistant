"""Hybrid search that is always scoped to one case.

`search_case` is the only function the app and the agents' search tool use to
query the index. It requires a `case_id` and always applies the filter, so a
caller cannot forget it and a prompt cannot remove it (ADR 0003).
"""

import re
from collections.abc import Iterable
from typing import Any, Protocol

from azure.search.documents.models import VectorizedQuery
from pydantic import BaseModel

# Case ids are ours (for example "case-001"). Allowing only these characters
# means a value can never break out of the quoted OData string below.
_CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SELECT_FIELDS = ["chunk_id", "case_id", "doc_id", "page", "section", "text"]


class SearchHit(BaseModel):
    chunk_id: str
    case_id: str
    doc_id: str
    page: int
    section: str
    text: str
    score: float


class SupportsSearch(Protocol):
    """The one SearchClient method we use. Lets tests pass a fake client."""

    def search(self, search_text: str | None = None, **kwargs: Any) -> Iterable[dict[str, Any]]: ...


def case_filter(case_id: str) -> str:
    if not _CASE_ID.fullmatch(case_id):
        raise ValueError(f"Invalid case_id: {case_id!r}")
    return f"case_id eq '{case_id}'"


def search_case(
    client: SupportsSearch,
    case_id: str,
    query: str,
    query_vector: list[float],
    top: int = 5,
) -> list[SearchHit]:
    """Keyword (BM25) plus vector search, merged by the service (RRF)."""
    results = client.search(
        search_text=query,
        vector_queries=[
            VectorizedQuery(vector=query_vector, k_nearest_neighbors=top, fields="embedding")
        ],
        filter=case_filter(case_id),
        # Filter before the vector search so all `top` results come from this case.
        vector_filter_mode="preFilter",
        select=SELECT_FIELDS,
        top=top,
    )
    hits: list[SearchHit] = []
    for doc in results:
        hits.append(SearchHit(**{k: doc[k] for k in SELECT_FIELDS}, score=doc["@search.score"]))
    return hits
