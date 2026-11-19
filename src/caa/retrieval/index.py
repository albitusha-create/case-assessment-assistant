"""Schema for the single `case-chunks` index (see ADR 0003).

Every chunk carries `case_id` as a filterable field, which is what lets one
index serve all cases while each query only sees one case.
"""

from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small
VECTOR_PROFILE = "hnsw-default"


def build_index(name: str) -> SearchIndex:
    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="case_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="doc_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True),
        SearchableField(name="section", analyzer_name="en.microsoft"),
        SearchableField(name="text", analyzer_name="en.microsoft"),
        SearchField(
            name="embedding",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name=VECTOR_PROFILE,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name=VECTOR_PROFILE, algorithm_configuration_name="hnsw")],
    )
    return SearchIndex(name=name, fields=fields, vector_search=vector_search)


def ensure_index(client: SearchIndexClient, name: str) -> None:
    """Create the index, or update it in place if the schema allows."""
    client.create_or_update_index(build_index(name))
