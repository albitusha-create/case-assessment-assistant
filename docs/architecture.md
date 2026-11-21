# Architecture

## Components

```mermaid
flowchart LR
    CW[Caseworker] --> UI
    SV[Supervisor] --> UI
    subgraph ACA[Azure Container Apps: FastAPI + UI]
        UI[Web UI and API] --> ING[Step 1: Ingest and index]
        ING --> EXT[Step 2: Extract facts]
        EXT --> DRA[Step 3: Drafting agent call]
        DRA --> QA[Step 4: QA agent call]
        QA --> REV[Step 5: Human review and approval]
        RULES[[rules: deterministic tools]]
    end
    ING --> BLOB[(Blob Storage)]
    ING --> DI[Document Intelligence]
    ING --> SRCH[(AI Search: one index, case filter)]
    EXT --> FDY[Foundry: agents and models]
    EXT -.-> APIM[APIM AI gateway, optional]
    APIM -.-> FDY
    DRA --> FDY
    QA --> FDY
    FDY -. function calls .-> RULES
    REV --> COS[(Cosmos DB: cases, drafts, audit)]
    ACA -. telemetry .-> AI[App Insights and Foundry tracing]
    ENTRA[Entra ID] -. sign-in and app roles .-> UI
    GH[GitHub Actions: OIDC, eval gate] -. azd deploy .-> ACA
```

Only steps 3 and 4 are agents. Ingestion, extraction orchestration, rules and approval are deterministic code or a human step. All service calls use a managed identity. API Management is optional (dashed): it is off by default to save cost, and `DEPLOY_APIM=true` puts it in front of direct model calls (extraction and embeddings).

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
    App->>Audit: drafted (facts, dropped citations)
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

## Integration: the agency's system of record

Workers submit the assessment in the agency's own case management system, not in this app. The repo includes a mock of that system at `/portal` (its own pages, state and REST API v1) and integrates with it as a client. See [ADR 0006](adr/0006-integrate-with-the-system-of-record.md).

```mermaid
sequenceDiagram
    actor CW as Caseworker
    actor SV as Supervisor
    participant App as Case Assessment Assistant
    participant Portal as Agency portal (mock)
    participant Audit as Cosmos audit log

    CW->>App: Run assessment
    App->>Portal: GET /cases/{id}
    App->>Audit: portal_case_pulled
    Note over App: extract, draft, QA (as above)
    SV->>App: Approve
    App->>Portal: GET form schema, PUT /cases/{id}/assessment/draft (Idempotency-Key)
    Portal-->>App: 200 draft saved (409 if the worker already edited or submitted)
    App->>Audit: portal_draft_pushed
    CW->>Portal: Review, edit, tick attestation, Submit
    Portal->>App: POST webhook, HMAC signed
    App->>Audit: submitted_in_portal (sections changed by worker)
```

- **No submit in the API.** Only a signed-in worker submits, in the portal.
- **Portal-side rules** hold for every caller: clinical sections and the self-rating cannot be pre-filled, a form the worker edited or submitted is never overwritten, and saves are idempotent.
- **MCP tools** at `/mcp` wrap the same client: four read tools and `portal_send_approved_draft(case_id)`, which runs the approval check. The endpoint answers only requests addressed to localhost.
- **In Azure** the mock runs in the same container. The client calls it over `127.0.0.1`, so Easy Auth, which guards ingress, is not in the path. `PORTAL_BASE_URL` points the same client at a real external system.
