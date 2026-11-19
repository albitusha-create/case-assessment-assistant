# 0003. One search index, filtered per case

- Status: accepted
- Date: 2026-11-19

## Context

Agents must only see documents from the case they are working on. Every claim must cite a document and page. The budget favors the Azure AI Search Free tier, which allows three indexes.

## Decision

Use one Azure AI Search index, `case-chunks`. Each chunk carries `case_id` (filterable), `doc_id`, `page`, `section`, `chunk_id`, text and a vector. Every query, including the agents' search tool, applies `case_id eq '<id>'` in code; the agents cannot remove it. Queries are hybrid: keyword (BM25) plus vector. Embeddings are computed in our ingestion code.

## Alternatives considered

- **Index per case.** Strong isolation but hits the Free tier limit at three cases and adds index lifecycle work.
- **Integrated vectorization and indexers.** Less code, but hides the chunking and embedding steps we want to explain. A production option.
- **Semantic ranker.** Better ranking, but needs a paid tier. A stretch item.

## Consequences

- Isolation depends on the filter always being applied, so the search function takes `case_id` as a required argument and has a test.
- Page-level citations come straight from Document Intelligence layout output.
- In production, add security trimming by user (on-behalf-of identity or group filters) on top of the case filter.
