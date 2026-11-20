# Architecture

## Components

```mermaid
flowchart LR
    CW[Caseworker] --> UI
    SV[Supervisor] --> UI
    subgraph ACA[Azure Container Apps: FastAPI + UI]
        UI[Web UI and API] --> ING[1. Ingest and index]
        ING --> EXT[2. Extract facts]
        EXT --> DRA[3. Drafting agent call]
        DRA --> QA[4. QA agent call]
        QA --> REV[5. Human review and approval]
        RULES[[rules: deterministic tools]]
    end
    ING --> BLOB[(Blob Storage)]
    ING --> DI[Document Intelligence]
    ING --> SRCH[(AI Search: one index, case filter)]
    EXT --> APIM[APIM AI gateway]
    APIM --> FDY[Foundry: agents and models]
    DRA --> FDY
    QA --> FDY
    FDY -. function calls .-> RULES
    REV --> COS[(Cosmos DB: cases, drafts, audit)]
    ACA -. telemetry .-> AI[App Insights and Foundry tracing]
    ENTRA[Entra ID] -. sign-in and app roles .-> UI
    GH[GitHub Actions: OIDC, eval gate] -. azd deploy .-> ACA
```

Only steps 3 and 4 are agents. Ingestion, extraction orchestration, rules and approval are deterministic code or a human step. All service calls use a managed identity.

## Request flow: generate and review a draft

```mermaid
sequenceDiagram
    actor CW as Caseworker
    actor SV as Supervisor
    participant App as FastAPI orchestrator
    participant Rules as rules package
    participant Draft as Drafting agent (Foundry)
    participant QA as QA agent (Foundry)
    participant Search as AI Search
    participant Audit as Cosmos audit log

    CW->>App: Generate draft for case
    App->>Rules: get_required_sections(type)
    App->>Draft: Draft sections (case id, sections, extracted facts)
    Draft->>App: function call: search_case_documents
    App->>Search: hybrid query with case_id filter
    Search-->>App: chunks with page numbers
    App-->>Draft: tool result
    Draft-->>App: Draft with cited claims
    App->>Audit: draft_generated (agent version, model)
    App->>Rules: rule checks (sections, elements, citations, deadline, determinations)
    App->>QA: Judge the agent items on the checklist
    QA->>App: function call: get_chunks (cited text)
    App-->>QA: chunks from this case only
    QA-->>App: findings per item (unreported items fail)
    App->>Audit: qa_completed
    App-->>CW: Draft and QA report
    SV->>App: Approve, return with comment, or dismiss an AI-judged finding with a reason
    App->>Audit: approved / returned / finding_dismissed (user, time, reason)
```
